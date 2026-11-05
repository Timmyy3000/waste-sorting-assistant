"""Subsystem B – Data & Rules (owner: Caleb).

Stores every scan and the disposal rules per region, and gives the other
subsystems a clean way to read them. Nobody outside this file writes SQL.
"""

import csv
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import pymysql  # MySQL driver (HT3), installed from requirements.txt

from app.pipeline import Processor, ScanEvent  # Timi's HT2 base classes (subsystem A)

# The only allowed waste categories. The same 4 strings are in schema.sql (CHECK).
CATEGORIES = ("recyclable", "compostable", "landfill", "unknown")

# schema.sql sits next to this file, so this works from any working directory (and in Docker).
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
MYSQL_SCHEMA_PATH = Path(__file__).parent / "schema_mysql.sql"
RULES_CSV_PATH = Path(__file__).parent.parent / "data" / "rules_seed.csv"


def _clean_text(value: str, field: str) -> str:
    """Return the text without outer spaces. Refuse anything that is not a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string, got {value!r}")
    return value.strip()


def _check_category(value: str) -> str:
    """Return the category if it is one of the 4 allowed ones, else raise."""
    if value not in CATEGORIES:
        raise ValueError(f"Unknown category: {value!r}. Allowed: {', '.join(CATEGORIES)}")
    return value


class Scan:
    """One saved scan: what was photographed, where, when, and how it was classified."""

    def __init__(
        self,
        id: int | None,
        timestamp: datetime,
        region: str,
        category: str,
        material: str,
        confidence: float,
        corrected: bool = False,
    ) -> None:
        # Each assignment below goes through the matching setter, so it is validated.
        self.id = id
        self.timestamp = timestamp
        self.region = region
        self.category = category
        self.material = material
        self.confidence = confidence
        self.corrected = corrected

    @property
    def id(self) -> int | None:
        """Database id. None until the scan has been saved."""
        return self._id

    @id.setter
    def id(self, value: int | None) -> None:
        if value is not None and not isinstance(value, int):
            raise ValueError(f"id must be an int or None, got {value!r}")
        self._id = value

    @property
    def timestamp(self) -> datetime:
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value: datetime) -> None:
        if not isinstance(value, datetime):
            raise ValueError(f"timestamp must be a datetime, got {value!r}")
        self._timestamp = value

    @property
    def region(self) -> str:
        return self._region

    @region.setter
    def region(self, value: str) -> None:
        self._region = _clean_text(value, "region")

    @property
    def category(self) -> str:
        return self._category

    @category.setter
    def category(self, value: str) -> None:
        self._category = _check_category(value)

    @property
    def material(self) -> str:
        return self._material

    @material.setter
    def material(self, value: str) -> None:
        self._material = _clean_text(value, "material")

    @property
    def confidence(self) -> float:
        return self._confidence

    @confidence.setter
    def confidence(self, value: float) -> None:
        if not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
            raise ValueError(f"confidence must be a number between 0 and 1, got {value!r}")
        self._confidence = float(value)

    @property
    def corrected(self) -> bool:
        """True if the user changed the category the AI suggested."""
        return self._corrected

    @corrected.setter
    def corrected(self, value: bool) -> None:
        self._corrected = bool(value)  # the DB stores 0/1, Python uses False/True

    def __repr__(self) -> str:
        return (
            f"Scan(id={self._id}, {self._timestamp:%Y-%m-%d %H:%M}, {self._region!r}, "
            f"{self._category!r}, {self._material!r}, {self._confidence:.2f}, "
            f"corrected={self._corrected})"
        )


class RecyclingRule:
    """The disposal rule for one category in one region (one row of the rules table)."""

    def __init__(self, region: str, category: str, bin: str, instructions: str) -> None:
        self.region = region
        self.category = category
        self.bin = bin
        self.instructions = instructions

    @property
    def region(self) -> str:
        return self._region

    @region.setter
    def region(self, value: str) -> None:
        self._region = _clean_text(value, "region")

    @property
    def category(self) -> str:
        return self._category

    @category.setter
    def category(self, value: str) -> None:
        self._category = _check_category(value)

    @property
    def bin(self) -> str:
        """Name of the bin, e.g. 'Gelbe Tonne'."""
        return self._bin

    @bin.setter
    def bin(self, value: str) -> None:
        self._bin = _clean_text(value, "bin")

    @property
    def instructions(self) -> str:
        return self._instructions

    @instructions.setter
    def instructions(self, value: str) -> None:
        self._instructions = _clean_text(value, "instructions")

    def __repr__(self) -> str:
        return f"RecyclingRule({self._region!r}, {self._category!r}, bin={self._bin!r})"


class Database:
    """Owns the connection to one SQLite database, creates its tables and runs ALL SQL.

    path=":memory:" gives a throw-away database in RAM (used by tests);
    a file name like "data/waste.db" gives a database that is kept on disk.
    MySQLDatabase (below) inherits from this class and changes only what MySQL does differently.
    """

    schema_path = SCHEMA_PATH  # class attribute: which schema file create_tables() runs

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._connection = None  # opened by connect()

    @property
    def path(self) -> str:
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        if self.is_connected:
            raise ValueError("Close the database before changing its path")
        self._path = _clean_text(value, "path")

    @property
    def is_connected(self) -> bool:
        """True while a connection is open (read-only, no setter)."""
        return self._connection is not None

    @property
    def connection(self):
        """The open connection. Connects first if needed."""
        if self._connection is None:
            self.connect()
        return self._connection

    def connect(self):
        """Open the connection (does nothing if it is already open)."""
        if self._connection is None:
            self._connection = self._open_connection()
        return self._connection

    def _open_connection(self):
        """SQLite version. MySQLDatabase overrides this method."""
        # check_same_thread=False: Flask may use the connection from another thread.
        connection = sqlite3.connect(self._path, check_same_thread=False)
        connection.row_factory = sqlite3.Row  # rows can be read by column name
        return connection

    def _convert_sql(self, sql: str) -> str:
        """Our SQL is written with ? placeholders. SQLite understands them, so no change.

        This is the ONE place where placeholders are handled (MySQLDatabase overrides it).
        """
        return sql

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Run one INSERT/UPDATE/DELETE in its own transaction. Returns the new row id."""
        return self.execute_all([(sql, params)])

    def execute_all(self, statements: list[tuple[str, tuple]]) -> int:
        """Run several (sql, params) statements in ONE transaction: all succeed or none.

        Returns the row id of the last INSERT.
        """
        cursor = self.connection.cursor()
        try:
            for sql, params in statements:
                cursor.execute(self._convert_sql(sql), params)
            self.connection.commit()  # save everything
        except Exception:
            self.connection.rollback()  # undo everything, then let the error continue
            raise
        return cursor.lastrowid

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Run a SELECT and return every row as a dict: {"column name": value}."""
        cursor = self.connection.cursor()
        cursor.execute(self._convert_sql(sql), params)
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the connection. For ":memory:" this also deletes all data."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def create_tables(self) -> None:
        """Setup method: run the schema file. Safe to call again (CREATE TABLE IF NOT EXISTS)."""
        schema = self.schema_path.read_text(encoding="utf-8")
        # The file holds several statements separated by ";" - run them one by one.
        statements = [(sql, ()) for sql in schema.split(";") if sql.strip()]
        self.execute_all(statements)

    def __enter__(self) -> "Database":
        """Start of a 'with Database(...) as db:' block: connect and hand back the object."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """End of the 'with' block, even after an error: close the connection."""
        self.close()

    def __repr__(self) -> str:
        state = "connected" if self.is_connected else "closed"
        return f"{type(self).__name__}({self._path!r}, {state})"


class MySQLDatabase(Database):
    """A Database on a MySQL server (HT3). Same public methods as Database,
    so the repositories work with both without any change (polymorphism).
    """

    schema_path = MYSQL_SCHEMA_PATH  # overrides the class attribute of Database

    def __init__(self, host: str, user: str, password: str, name: str, port: int = 3306) -> None:
        super().__init__(f"mysql://{user}@{host}:{port}/{name}")  # a label only, no password
        self._host = host
        self._user = user
        self._password = password
        self._name = name
        self._port = port

    @property
    def host(self) -> str:
        return self._host

    @property
    def name(self) -> str:
        """Name of the database (schema) on the MySQL server."""
        return self._name

    def _open_connection(self):
        """MySQL version: connect over the network with pymysql."""
        return pymysql.connect(
            host=self._host,
            user=self._user,
            password=self._password,
            database=self._name,
            port=self._port,
            charset="utf8mb4",  # full UTF-8, e.g. the "ü" in Restmülltonne
            cursorclass=pymysql.cursors.DictCursor,  # rows come back as dicts
        )

    def _convert_sql(self, sql: str) -> str:
        """MySQL uses %s instead of ? as the placeholder."""
        return sql.replace("?", "%s")


def create_database() -> Database:
    """Choose the database from environment variables (used by the Flask app).

    DB_HOST set     -> MySQLDatabase (needs DB_USER, DB_PASSWORD, DB_NAME, optional DB_PORT)
    DB_HOST not set -> SQLite file DB_PATH (default "data/waste.db")
    """
    host = os.environ.get("DB_HOST")
    if host:
        return MySQLDatabase(
            host=host,
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            name=os.environ.get("DB_NAME", "waste_sorting"),
            port=int(os.environ.get("DB_PORT", "3306")),
        )
    return Database(os.environ.get("DB_PATH", "data/waste.db"))


class BaseRepository(ABC):
    """Shared code for all repositories. A repository moves objects in and out of ONE table.

    Abstract: you cannot create a BaseRepository itself, only a subclass that
    implements _row_to_object().
    """

    def __init__(self, database: Database) -> None:
        self._database = database
        self._database.create_tables()  # make sure the tables exist (safe to repeat)

    @property
    def database(self) -> Database:
        """The Database this repository uses (read-only)."""
        return self._database

    def _execute(self, sql: str, params: tuple = ()) -> int:
        """Run one INSERT/UPDATE/DELETE in a transaction and return the new row id.

        The values go in 'params' and replace the '?' placeholders, never into the SQL text.
        """
        return self._database.execute(sql, params)  # works for SQLite and MySQL

    def _query(self, sql: str, params: tuple = ()) -> list:
        """Run a SELECT and turn every row into an object with _row_to_object()."""
        rows = self._database.query(sql, params)
        return [self._row_to_object(row) for row in rows]

    @abstractmethod
    def _row_to_object(self, row: dict) -> object:
        """Turn one database row into a Python object. Each subclass decides how."""


class ScanRepository(BaseRepository):
    """Saves and reads scans. C and D read scans ONLY through get_scans()."""

    def save_scan(self, scan: Scan) -> int:
        """Insert a new scan, store the new id on the object and return it."""
        if scan.id is not None:
            raise ValueError(f"Scan already saved with id {scan.id}")
        new_id = self._execute(
            "INSERT INTO scans (timestamp, region, category, material, confidence, corrected) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                scan.timestamp.isoformat(),  # datetime -> text, e.g. '2026-11-05T14:30:00'
                scan.region,
                scan.category,
                scan.material,
                scan.confidence,
                int(scan.corrected),  # True/False -> 1/0
            ),
        )
        scan.id = new_id
        return new_id

    def get_scans(
        self,
        region: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Scan]:
        """Return scans, oldest first. Every filter is optional; start and end days are included."""
        conditions = []
        params = []
        if region is not None:
            conditions.append("region = ?")
            params.append(region)
        if start is not None:
            conditions.append("timestamp >= ?")
            params.append(start.isoformat())  # '2026-11-01' = start of that day
        if end is not None:
            conditions.append("timestamp < ?")
            params.append((end + timedelta(days=1)).isoformat())  # before the NEXT day

        sql = "SELECT * FROM scans"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY timestamp"
        return self._query(sql, tuple(params))

    def _row_to_object(self, row: dict) -> Scan:
        """One row of the scans table -> Scan object (text -> datetime, 0/1 -> bool)."""
        return Scan(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            region=row["region"],
            category=row["category"],
            material=row["material"],
            confidence=row["confidence"],
            corrected=bool(row["corrected"]),
        )


class RuleRepository(BaseRepository):
    """Loads and reads the disposal rules (one per region + category)."""

    def load_from_csv(self, path: str | Path = RULES_CSV_PATH) -> int:
        """Setup method: replace all rules with the ones in the CSV file. Returns how many.

        All or nothing: every line is checked first, and the database is changed in
        one transaction, so a bad file never leaves half the rules behind.
        """
        rules = []
        with open(path, newline="", encoding="utf-8") as file:
            for line_number, row in enumerate(csv.DictReader(file), start=2):  # line 1 = header
                try:
                    rules.append(
                        RecyclingRule(row["region"], row["category"], row["bin"], row["instructions"])
                    )
                except (KeyError, ValueError) as error:
                    raise ValueError(f"{path}, line {line_number}: {error}") from error

        insert = "INSERT INTO rules (region, category, bin, instructions) VALUES (?, ?, ?, ?)"
        statements = [("DELETE FROM rules", ())]
        statements += [(insert, (r.region, r.category, r.bin, r.instructions)) for r in rules]
        self.database.execute_all(statements)  # one transaction: all succeed, or nothing changes
        return len(rules)

    def get_rule(self, region: str, category: str) -> RecyclingRule:
        """Return the rule for this region and category. Raises LookupError if there is none."""
        rules = self._query(
            "SELECT * FROM rules WHERE region = ? AND category = ?", (region, category)
        )
        if not rules:
            raise LookupError(f"No rule for region {region!r} and category {category!r}")
        return rules[0]  # the primary key (region, category) guarantees at most one

    def get_regions(self) -> list[str]:
        """All regions that have rules, A-Z (e.g. for the region drop-down on the upload page)."""
        rows = self.database.query("SELECT DISTINCT region FROM rules ORDER BY region")
        return [row["region"] for row in rows]

    def _row_to_object(self, row: dict) -> RecyclingRule:
        """One row of the rules table -> RecyclingRule object."""
        return RecyclingRule(row["region"], row["category"], row["bin"], row["instructions"])


class DbSink(Processor):
    """Pipeline step (HT2) that saves every ScanEvent as a Scan, then passes the event on.

    Because it yields each event again, it can be the last step of a pipeline or sit
    in the middle:  Pipeline(source) | DbSink(scan_repository) | another_step
    """

    def __init__(self, repository: ScanRepository) -> None:
        self._repository = repository
        self._saved = 0  # how many events this sink has saved so far

    @property
    def repository(self) -> ScanRepository:
        """The ScanRepository the events are saved with (read-only)."""
        return self._repository

    @property
    def saved(self) -> int:
        """Number of events saved so far (read-only, only process() changes it)."""
        return self._saved

    def process(self, events: Iterator[ScanEvent]) -> Iterator[ScanEvent]:
        """Generator: save one event, yield it, then wait until the next one is asked for."""
        for event in events:
            self._repository.save_scan(self._to_scan(event))
            self._saved += 1
            yield event

    def _to_scan(self, event: ScanEvent) -> Scan:
        """ScanEvent (message in the stream) -> Scan (record for the database, validated)."""
        return Scan(None, event.timestamp, event.region, event.category, event.material, event.confidence)


if __name__ == "__main__":
    # Demo for the HT1 video. Run it with:  python -m app.db
    with Database() as db:  # in-memory database, closed automatically at the end
        rules = RuleRepository(db)  # both repositories share the SAME Database object
        scans = ScanRepository(db)

        print(f"Loaded {rules.load_from_csv()} rules for {rules.get_regions()}\n")

        scans.save_scan(Scan(None, datetime(2026, 11, 5, 9, 15), "Dortmund", "recyclable", "plastic bottle", 0.93))
        scans.save_scan(Scan(None, datetime(2026, 11, 5, 9, 20), "Munich", "compostable", "banana peel", 0.88))

        for scan in scans.get_scans():
            rule = rules.get_rule(scan.region, scan.category)
            print(scan)
            print(f"   -> {rule.bin}: {rule.instructions}\n")

    # Demo for the HT2 video: a stream of ScanEvents flows through DbSink into the database.
    print("=== HT2: stream -> DbSink -> database ===")
    with Database() as db:
        scans = ScanRepository(db)
        sink = DbSink(scans)
        events = [
            ScanEvent(datetime(2026, 11, 6, 8, 0), "Berlin", "recyclable", "tin can", 0.95),
            ScanEvent(datetime(2026, 11, 6, 8, 5), "Dortmund", "landfill", "chip bag", 0.81),
            ScanEvent(datetime(2026, 11, 6, 8, 10), "Munich", "compostable", "apple core", 0.67),
        ]
        for event in sink.process(iter(events)):  # pulls ONE event at a time through the generator
            print(f"saved {sink.saved}: {event.region} / {event.category} / {event.material}")

        print(f"\nRead back with get_scans(): {len(scans.get_scans())} scans")
        for scan in scans.get_scans():
            print("  ", scan)
