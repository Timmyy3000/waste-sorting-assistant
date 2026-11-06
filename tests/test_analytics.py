"""Unit tests for subsystem C (Dashboard & Analytics)."""

from datetime import datetime

import pytest

from app.analytics import (
    ChartRenderer,
    InvalidAnalyticsInputError,
    NoDataError,
    RecyclingStats,
    StatsCalculator,
    build_dashboard_payload,
)
from app.db import Database, Scan, ScanRepository


@pytest.fixture
def db():
    """In-memory SQLite for one test."""
    database = Database()
    yield database
    database.close()


@pytest.fixture
def scan_repo(db):
    return ScanRepository(db)


def test_recycling_rate_from_saved_scans(scan_repo):
    """Recycling rate = (recyclable + compostable) / total from get_scans() data."""
    scan_repo.save_scan(
        Scan(None, datetime(2026, 11, 6, 10, 0), "Dortmund", "recyclable", "bottle", 0.9)
    )
    scan_repo.save_scan(
        Scan(None, datetime(2026, 11, 6, 10, 1), "Dortmund", "landfill", "wrapper", 0.8)
    )
    calculator = StatsCalculator(scan_repo)
    stats = calculator.get_stats()
    assert stats.total_scans == 2
    assert stats.recycling_rate == 0.5


def test_empty_stats_have_zero_recycling_rate(scan_repo):
    """No scans: rate is 0.0 (defined), not a division error."""
    stats = StatsCalculator(scan_repo).get_stats()
    assert stats.total_scans == 0
    assert stats.recycling_rate == 0.0


def test_invalid_category_raises_invalid_analytics_input():
    """Unknown category on RecyclingStats raises InvalidAnalyticsInputError."""
    stats = RecyclingStats()
    with pytest.raises(InvalidAnalyticsInputError):
        stats.increment_category_count("hazardous")


def test_chart_png_and_no_data_requirement(scan_repo):
    """Chart produces a PNG; require_scans raises NoDataError when the filter is empty."""
    scan_repo.save_scan(
        Scan(None, datetime(2026, 11, 6, 11, 0), "Munich", "compostable", "peel", 0.85)
    )
    stats = StatsCalculator(scan_repo).get_stats()
    renderer = ChartRenderer()
    renderer.setup()
    png = renderer.render_category_bar_chart(stats)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    with pytest.raises(NoDataError):
        build_dashboard_payload(scan_repo, region="Nowhereville", require_scans=True)
