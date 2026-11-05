"""Run a source through a chain of stream processors."""

from collections.abc import Iterator

from app.pipeline import Processor, ScanEvent, Source


class Pipeline:
    """Connect a source to processors without consuming the stream early."""

    def __init__(self, source: Source, processors: list[Processor] | None = None) -> None:
        self._source = source
        self._processors = list(processors) if processors is not None else []

    def __or__(self, processor: Processor) -> "Pipeline":
        """Return a new pipeline with one extra processor."""
        return Pipeline(self._source, self._processors + [processor])

    def run(self) -> Iterator[ScanEvent]:
        """Connect the steps and return the resulting event iterator."""
        events = iter(self._source)
        for processor in self._processors:
            events = processor.process(events)
        return events

    def __iter__(self) -> Iterator[ScanEvent]:
        """Allow the pipeline itself to be used in a for loop."""
        return self.run()
