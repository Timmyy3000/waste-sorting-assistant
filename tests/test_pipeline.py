"""Tests for A's HT2 stream processors (ConfidenceFilter, MaterialRouter)."""

from datetime import datetime

from app.ai_services import ConfidenceFilter, MaterialRouter
from app.pipeline import ScanEvent


def event(confidence=0.9, tags=(), bbox=None):
    return ScanEvent(datetime(2026, 11, 7), "Dortmund", "recyclable", "item", confidence, tags, bbox)


def test_confidence_filter_drops_low_confidence_predictions():
    step = ConfidenceFilter(min_confidence=0.6)
    kept = list(step.process(iter([event(0.9), event(0.3), event(0.6)])))

    assert [e.confidence for e in kept] == [0.9, 0.6]
    assert step.dropped == 1


def test_material_router_sets_material_code_and_route():
    router = MaterialRouter(max_box_size=300)
    events = [
        event(tags=("bottle", "clear plastic"), bbox=(0, 0, 100, 120)),
        event(tags=("jug", "milk jug"), bbox=(0, 0, 80, 80)),
        event(tags=("can", "aluminium"), bbox=(0, 0, 350, 90)),  # too big for a lane
        event(tags=("ceramic",)),
    ]
    routed = [(e.material_code, e.route) for e in router.process(iter(events))]

    assert routed == [
        ("PET", "LANE-1-PLASTIC"),
        ("HDPE", "LANE-1-PLASTIC"),
        ("ALU", "MANUAL"),
        ("OTHER", "LANE-RESIDUAL"),
    ]
