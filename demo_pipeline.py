"""Demonstrate a pipeline without an API key or database."""

from collections.abc import Iterator

from app.ai_services import SimulatedScanSource
from app.pipeline import Processor, ScanEvent
from app.pipeline_runner import Pipeline


class DemoRegionFilter(Processor):
    """Temporary stand-in until the team's filter is available."""

    def __init__(self, region: str) -> None:
        self._region = region

    def process(self, events: Iterator[ScanEvent]) -> Iterator[ScanEvent]:
        """Yield only events from the chosen region."""
        for event in events:
            if event.region == self._region:
                yield event


if __name__ == "__main__":
    source = SimulatedScanSource(count=10, seed=1)
    for event in Pipeline(source) | DemoRegionFilter("Dortmund"):
        print(f"{event.region}: {event.category} ({event.material})")
