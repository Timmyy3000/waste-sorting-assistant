"""Run the integrated HT2 stream through analytics and database processors."""

from app.ai_services import SimulatedScanSource
from app.analytics import CategoryTally, RegionFilter, RunningRecyclingRateTracker
from app.db import Database, DbSink, ScanRepository
from app.pipeline_runner import Pipeline


if __name__ == "__main__":
    with Database() as database:
        tally = CategoryTally()
        rate = RunningRecyclingRateTracker()
        sink = DbSink(ScanRepository(database))
        pipeline = (
            Pipeline(SimulatedScanSource(count=10, seed=1))
            | RegionFilter("Dortmund")
            | tally
            | rate
            | sink
        )
        for event in pipeline:
            print(f"{event.region}: {event.category} ({event.material})")
        print(f"Saved: {sink.saved}; counts: {tally.counts}; rate: {rate.running_rate:.0%}")
