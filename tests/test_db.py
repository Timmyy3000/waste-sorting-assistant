"""Unit tests for subsystem B (Data & Rules).

Every test gets a fresh, empty in-memory SQLite database from the fixtures below,
so the tests are fast, need no MySQL server and cannot influence each other.
"""

from datetime import date, datetime

import pytest

from app.db import (
    Database,
    DatabaseError,
    InvalidScanError,
    RuleNotFoundError,
    RuleRepository,
    Scan,
    ScanRepository,
)


@pytest.fixture
def db():
    """A new in-memory database for ONE test. Closed again after the test (teardown)."""
    database = Database()  # ":memory:" -> gone after close()
    yield database  # the test runs here
    database.close()


@pytest.fixture
def scan_repo(db):
    """A ScanRepository on the test database (this fixture uses the db fixture)."""
    return ScanRepository(db)


def test_save_scan_and_read_it_back(scan_repo):
    """Black box: what goes in through save_scan() comes out of get_scans() unchanged."""
    scan = Scan(None, datetime(2026, 11, 6, 9, 30), "Dortmund", "recyclable", "plastic bottle", 0.93)

    new_id = scan_repo.save_scan(scan)

    assert new_id == 1
    assert scan.id == 1  # save_scan() also stores the id on the object
    [loaded] = scan_repo.get_scans()  # exactly one scan in the database
    assert loaded.id == 1
    assert loaded.timestamp == datetime(2026, 11, 6, 9, 30)
    assert (loaded.region, loaded.category, loaded.material) == ("Dortmund", "recyclable", "plastic bottle")
    assert loaded.confidence == 0.93
    assert loaded.corrected is False


def test_get_scans_filters_by_region_and_dates(scan_repo):
    """Black box: region filter, start date and an INCLUDED end date (even at 23:59)."""
    scan_repo.save_scan(Scan(None, datetime(2026, 11, 1, 9, 0), "Dortmund", "recyclable", "can", 0.9))
    scan_repo.save_scan(Scan(None, datetime(2026, 11, 3, 12, 0), "Berlin", "compostable", "peel", 0.8))
    scan_repo.save_scan(Scan(None, datetime(2026, 11, 5, 23, 59), "Dortmund", "landfill", "nappy", 0.7))

    def ids(scans: list[Scan]) -> list[int]:
        return [scan.id for scan in scans]

    assert ids(scan_repo.get_scans()) == [1, 2, 3]  # no filter, oldest first
    assert ids(scan_repo.get_scans(region="Dortmund")) == [1, 3]
    assert ids(scan_repo.get_scans(start=date(2026, 11, 3))) == [2, 3]
    assert ids(scan_repo.get_scans(end=date(2026, 11, 5))) == [1, 2, 3]  # whole end day counts
    assert ids(scan_repo.get_scans("Dortmund", date(2026, 11, 2), date(2026, 11, 5))) == [3]
    assert scan_repo.get_scans(region="Hamburg") == []


def test_unknown_region_raises_rule_not_found(db):
    """Black box: get_rule() for a region that is not in the CSV raises RuleNotFoundError."""
    rules = RuleRepository(db)
    rules.load_from_csv()  # the real data/rules_seed.csv
    assert rules.get_rule("Dortmund", "landfill").bin == "Restmülltonne (grey)"  # a known one works

    with pytest.raises(RuleNotFoundError) as error_info:
        rules.get_rule("Hamburg", "recyclable")

    assert error_info.value.region == "Hamburg"  # the exception carries the details
    assert isinstance(error_info.value, DatabaseError)  # and belongs to our hierarchy


def test_invalid_category_is_rejected(db, scan_repo):
    """Gray box: Python refuses 'glass' (InvalidScanError), and so does the CHECK
    constraint of the scans table (DatabaseError), so nothing is ever saved.
    """
    with pytest.raises(InvalidScanError):
        Scan(None, datetime(2026, 11, 6), "Berlin", "glass", "jar", 0.9)

    # Bypass the Scan class and write SQL directly: the database itself must refuse it.
    with pytest.raises(DatabaseError, match="CHECK constraint"):
        db.execute(
            "INSERT INTO scans (timestamp, region, category, material, confidence) "
            "VALUES (?, ?, ?, ?, ?)",
            ("2026-11-06T10:00:00", "Berlin", "glass", "jar", 0.9),
        )

    assert scan_repo.get_scans() == []  # the table is still empty
