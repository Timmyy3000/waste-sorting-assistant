"""Run the integrated HT2 stream: optical-sorter events -> filter -> route -> analytics -> database."""

from app.ai_services import ConfidenceFilter, MaterialRouter, SimulatedScanSource
from app.analytics import CategoryTally, RegionFilter, RunningRecyclingRateTracker
from app.db import Database, DbSink, ScanRepository
from app.pipeline_runner import Pipeline


if __name__ == "__main__":
    with Database() as database:
        confident = ConfidenceFilter(min_confidence=0.6)
        tally = CategoryTally()
        rate = RunningRecyclingRateTracker()
        sink = DbSink(ScanRepository(database))
        pipeline = (
            Pipeline(SimulatedScanSource(count=10, seed=1))
            | confident
            | MaterialRouter()
            | RegionFilter("Dortmund")
            | tally
            | rate
            | sink
        )
        for event in pipeline:
            print(f"{event.region}: {event.material} ({event.confidence:.0%}) -> {event.material_code} -> {event.route}")
        print(f"Dropped as low-confidence: {confident.dropped}")
        print(f"Saved: {sink.saved}; counts: {tally.counts}; rate: {rate.running_rate:.0%}")
