"""Base classes for the stream-processing pipeline (HT2). Owner: Timi (A).

A Source produces a stream of ScanEvents. A Processor takes a stream and yields a new
stream (filtered, counted, saved ...). Every subsystem inherits from these classes,
so the pipeline runner (D) can treat all of them the same way (polymorphism).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator


@dataclass
class ScanEvent:
    """One waste scan flowing through the pipeline."""

    timestamp: datetime
    region: str
    category: str
    material: str
    confidence: float
    # Optical-sorter payload: visual tags and bounding box (x, y, width, height in pixels).
    tags: tuple[str, ...] = ()
    bbox: tuple[int, int, int, int] | None = None
    # Filled in by MaterialRouter: material code (e.g. PET, HDPE, ALU) and conveyor route.
    material_code: str = ""
    route: str = ""


class Source(ABC):
    """Produces a stream of ScanEvents. Subclasses must implement __iter__."""

    @abstractmethod
    def __iter__(self) -> Iterator[ScanEvent]: ...


class Processor(ABC):
    """Takes a stream of events and yields a (filtered or changed) stream."""

    @abstractmethod
    def process(self, events: Iterator[ScanEvent]) -> Iterator[ScanEvent]: ...
