"""Subsystem C – Dashboard & Analytics (owner: Onyedikachi Onah).

Aggregates scan history for charts and JSON-friendly stats. All scan rows are read
only through ``ScanRepository.get_scans()`` from subsystem B — this module never
opens a database connection or runs SQL.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator, Mapping
from datetime import date
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app.db import CATEGORIES, Scan, ScanRepository
from app.pipeline import Processor, ScanEvent

# Categories that count as diverted from landfill for a simple recycling-rate KPI.
_RECYCLING_STREAMS = frozenset({"recyclable", "compostable"})


class RecyclingStats:
    """Aggregated counts derived from ``Scan`` rows (per-category and headline KPIs)."""

    def __init__(self) -> None:
        self._category_counts: dict[str, int] = {c: 0 for c in CATEGORIES}
        self._total_scans: int = 0

    def setup_from_counts(self, counts: Mapping[str, int]) -> None:
        """Setup helper: replace counts from a mapping (validates category keys)."""
        for cat in CATEGORIES:
            n = int(counts.get(cat, 0))
            if n < 0:
                raise ValueError(f"Count for {cat!r} must be non-negative, got {n}")
            self.set_category_count(cat, n)

    @classmethod
    def from_scans(cls, scans: list[Scan]) -> RecyclingStats:
        """Build stats by walking scan rows (usually from ``get_scans()``)."""
        stats = cls()
        for scan in scans:
            stats.record_scan(scan)
        return stats

    def record_scan(self, scan: Scan) -> None:
        """Add one scan to the totals (mutates counts)."""
        self.increment_category_count(scan.category)
        self.total_scans = self.total_scans + 1

    def increment_category_count(self, category: str) -> None:
        """Increase the count for one category by one."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category!r}")
        self._category_counts[category] = self._category_counts[category] + 1

    @property
    def category_counts(self) -> dict[str, int]:
        """Copy of per-category totals (read-only snapshot)."""
        return dict(self._category_counts)

    def get_category_count(self, category: str) -> int:
        """Getter for a single bin in ``category_counts``."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category!r}")
        return self._category_counts[category]

    def set_category_count(self, category: str, value: int) -> None:
        """Setter for a single bin (used by ``setup_from_counts`` and tests)."""
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category!r}")
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"count must be a non-negative int, got {value!r}")
        self._category_counts[category] = value
        self._recompute_total()

    @property
    def total_scans(self) -> int:
        return self._total_scans

    @total_scans.setter
    def total_scans(self, value: int) -> None:
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"total_scans must be a non-negative int, got {value!r}")
        self._total_scans = value

    def _recompute_total(self) -> None:
        self._total_scans = sum(self._category_counts.values())

    @property
    def recycling_rate(self) -> float:
        """Share of scans that are recyclable or compostable (0.0–1.0)."""
        if self._total_scans == 0:
            return 0.0
        diverted = sum(self._category_counts[c] for c in _RECYCLING_STREAMS)
        return diverted / self._total_scans


class StatsCalculator:
    """Computes :class:`RecyclingStats` using only ``ScanRepository.get_scans()``."""

    def __init__(self, repository: ScanRepository) -> None:
        self._repository = repository

    @property
    def repository(self) -> ScanRepository:
        """Scan data access facade from subsystem B (read-only)."""
        return self._repository

    @repository.setter
    def repository(self, value: ScanRepository) -> None:
        self._repository = value

    def setup(self) -> None:
        """Optional warm-up: touch the repository read path (no direct DB access here)."""
        self._repository.get_scans()

    def get_stats(
        self,
        region: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> RecyclingStats:
        """Return aggregates for optional region and/or inclusive date window."""
        scans = self._repository.get_scans(region=region, start=start, end=end)
        return RecyclingStats.from_scans(scans)


class ChartRenderer:
    """Renders matplotlib figures to PNG bytes for the dashboard."""

    def __init__(self, dpi: int = 110, figsize: tuple[float, float] = (6.0, 4.0)) -> None:
        self._dpi = dpi
        self._figsize = figsize

    @property
    def dpi(self) -> int:
        return self._dpi

    @dpi.setter
    def dpi(self, value: int) -> None:
        if not isinstance(value, int) or not (40 <= value <= 600):
            raise ValueError("dpi must be an int between 40 and 600")
        self._dpi = value

    @property
    def figsize(self) -> tuple[float, float]:
        return self._figsize

    @figsize.setter
    def figsize(self, value: tuple[float, float]) -> None:
        w, h = value
        if w <= 0 or h <= 0:
            raise ValueError("figsize must be positive")
        self._figsize = (float(w), float(h))

    def setup(self) -> None:
        """Apply a simple, readable style for small PNGs (falls back if name differs)."""
        for name in ("seaborn-v0_8-whitegrid", "ggplot"):
            try:
                plt.style.use(name)
                return
            except OSError:
                continue

    def render_category_bar_chart(self, stats: RecyclingStats) -> bytes:
        """PNG image bytes for a bar chart of per-category scan counts."""
        counts = stats.category_counts
        labels = list(CATEGORIES)
        values = [counts[c] for c in labels]

        figure, axis = plt.subplots(figsize=self._figsize, dpi=self._dpi)
        try:
            bars = axis.bar(labels, values, color=["#2ca02c", "#8c564b", "#7f7f7f", "#bcbd22"])
            axis.set_ylabel("Scans")
            axis.set_title("Scans per category")
            for bar, value in zip(bars, values, strict=True):
                if value > 0:
                    axis.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height(),
                        str(value),
                        ha="center",
                        va="bottom",
                        fontsize=8,
                    )
            figure.tight_layout()
            buffer = BytesIO()
            figure.savefig(buffer, format="png", bbox_inches="tight")
            return buffer.getvalue()
        finally:
            plt.close(figure)


# --- HT2: stream processors (inherit Timi's ``Processor`` base class) ---


class RegionFilter(Processor):
    """Keep only events whose ``region`` matches."""

    def __init__(self, region: str) -> None:
        self.region = region

    @property
    def region(self) -> str:
        return self._region

    @region.setter
    def region(self, value: str) -> None:
        text = value.strip() if isinstance(value, str) else ""
        if not text:
            raise ValueError("region must be a non-empty string")
        self._region = text

    def process(self, events: Iterator[ScanEvent]) -> Iterator[ScanEvent]:
        for event in events:
            if event.region == self._region:
                yield event


class CategoryTally(Processor):
    """Pass-through processor that counts how many events landed in each category."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {c: 0 for c in CATEGORIES}

    def setup(self) -> None:
        """Reset all category bins to zero."""
        self._counts = {c: 0 for c in CATEGORIES}

    @property
    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def process(self, events: Iterator[ScanEvent]) -> Iterator[ScanEvent]:
        for event in events:
            if event.category not in CATEGORIES:
                raise ValueError(f"Unknown category on event: {event.category!r}")
            self._counts[event.category] += 1
            yield event


class RunningRecyclingRateTracker(Processor):
    """Pass-through processor that tracks the running recycling rate (recyclable + compostable / all)."""

    def __init__(self) -> None:
        self._seen = 0
        self._diverted = 0

    def setup(self) -> None:
        """Clear counters before a new run."""
        self._seen = 0
        self._diverted = 0

    @property
    def running_rate(self) -> float:
        if self._seen == 0:
            return 0.0
        return self._diverted / self._seen

    def process(self, events: Iterator[ScanEvent]) -> Iterator[ScanEvent]:
        for event in events:
            self._seen += 1
            if event.category in _RECYCLING_STREAMS:
                self._diverted += 1
            yield event


def build_dashboard_payload(
    repository: ScanRepository,
    *,
    region: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, object]:
    """JSON-friendly dashboard data plus a PNG chart for Moye's dashboard route.

    ``repository`` must be a :class:`~app.db.ScanRepository` so scans are read only
    through ``get_scans()`` (subsystem B). Returns native Python types and a
    base64-encoded PNG for easy JSON or HTML embedding.
    """
    calculator = StatsCalculator(repository)
    stats = calculator.get_stats(region=region, start=start, end=end)
    renderer = ChartRenderer()
    renderer.setup()
    png_bytes = renderer.render_category_bar_chart(stats)
    return {
        "filters": {
            "region": region,
            "start": start.isoformat() if start is not None else None,
            "end": end.isoformat() if end is not None else None,
        },
        "total_scans": stats.total_scans,
        "recycling_rate": round(stats.recycling_rate, 4),
        "category_counts": stats.category_counts,
        "chart_png_base64": base64.b64encode(png_bytes).decode("ascii"),
    }
