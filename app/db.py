"""Subsystem B – Data & Rules (owner: Caleb).

Stores every scan and the disposal rules per region, and gives the other
subsystems a clean way to read them. Nobody outside this file writes SQL.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

# The only allowed waste categories. The same 4 strings are in schema.sql (CHECK).
CATEGORIES = ("recyclable", "compostable", "landfill", "unknown")

# schema.sql sits next to this file, so this works from any working directory (and in Docker).
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


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
    """Owns the connection to one SQLite database and creates its tables.

    path=":memory:" gives a throw-away database in RAM (used by tests);
    a file name like "data/waste.db" gives a database that is kept on disk.
    """

    def __init__(self, path: str = ":memory:") -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = None  # opened by connect()

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
    def connection(self) -> sqlite3.Connection:
        """The open connection. Connects first if needed."""
        if self._connection is None:
            self.connect()
        return self._connection

    def connect(self) -> sqlite3.Connection:
        """Open the connection (does nothing if it is already open)."""
        if self._connection is None:
            self._connection = sqlite3.connect(self._path)
            self._connection.row_factory = sqlite3.Row  # rows can be read by column name
        return self._connection

    def close(self) -> None:
        """Close the connection. For ":memory:" this also deletes all data."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def create_tables(self) -> None:
        """Setup method: run schema.sql. Safe to call again (CREATE TABLE IF NOT EXISTS)."""
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.connection:  # transaction: commit if OK, roll back on error
            self.connection.executescript(schema)

    def __enter__(self) -> "Database":
        """Start of a 'with Database(...) as db:' block: connect and hand back the object."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """End of the 'with' block, even after an error: close the connection."""
        self.close()

    def __repr__(self) -> str:
        state = "connected" if self.is_connected else "closed"
        return f"Database({self._path!r}, {state})"
