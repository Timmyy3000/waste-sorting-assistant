"""Recycling dashboard pages and shared JSON payload helpers."""

from datetime import date

from flask import Response, jsonify, render_template, request

from app.analytics import build_dashboard_payload
from app.db import RuleRepository, ScanRepository, create_database
from app.disposal import STREAMS
from app.routes.base import BaseBlueprint
from app.routes.errors import WebAppError
from app.scan_reviews import ReviewRepository, owner_hash


def dashboard_payload() -> dict:
    """Read filters and adapt subsystem C's payload to the agreed rate formula."""
    region = request.args.get("region", "").strip() or None
    try:
        start = date.fromisoformat(request.args["start"]) if request.args.get("start") else None
        end = date.fromisoformat(request.args["end"]) if request.args.get("end") else None
    except ValueError:
        raise WebAppError("Dates must use YYYY-MM-DD.") from None
    if start is not None and end is not None and start > end:
        raise WebAppError("The start date must not be after the end date.")
    with create_database() as database:
        repository = ScanRepository(database)
        payload = build_dashboard_payload(
            repository, region=region, start=start, end=end
        )
        scans = repository.get_scans(region=region, start=start, end=end)
        reviews = ReviewRepository(database)
        payload["stream_counts"] = reviews.stream_counts([scan.id for scan in scans])
        payload["corrected_scans"] = sum(scan.corrected for scan in scans)
        specialist = sum(payload["stream_counts"][route] for route in
                         ("electronics", "hazardous", "bulky", "vehicle"))
        payload["unresolved_scans"] = payload["category_counts"]["unknown"] - specialist
    # C supplies the counts; unknown items must not enter the rate denominator.
    counts = payload["category_counts"]
    known = payload["total_scans"] - counts["unknown"]
    diverted = counts["recyclable"] + counts["compostable"]
    payload["recycling_rate"] = round(diverted / known, 4) if known else 0.0
    return payload


class DashboardBlueprint(BaseBlueprint):
    """Provide the statistics page and a JSON view of the same data."""

    def __init__(self) -> None:
        super().__init__("dashboard", "/dashboard")

    def register_routes(self) -> None:
        """Register the HTML and JSON dashboard endpoints."""
        self.blueprint.add_url_rule("", view_func=self.dashboard)
        self.blueprint.add_url_rule("/data", view_func=self.dashboard_data)

    def dashboard(self) -> str:
        """Render real statistics, chart and available region filters."""
        payload = dashboard_payload()
        with create_database() as database:
            regions = RuleRepository(database).get_regions()
            history = ReviewRepository(database).history(owner_hash(),
                region=request.args.get("region", "").strip() or None,
                start=date.fromisoformat(request.args["start"]) if request.args.get("start") else None,
                end=date.fromisoformat(request.args["end"]) if request.args.get("end") else None)
        return render_template(
            "dashboard.html", payload=payload, regions=regions, history=history, streams=STREAMS,
            selected_region=request.args.get("region", ""),
            start=request.args.get("start", ""), end=request.args.get("end", ""),
        )

    def dashboard_data(self) -> Response:
        """Return the dashboard payload as JSON."""
        return jsonify(dashboard_payload())
