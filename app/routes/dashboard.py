"""Routes for the recycling dashboard."""

from datetime import date

from flask import Response, jsonify, render_template, request

from app.analytics import build_dashboard_payload
from app.db import RuleRepository, ScanRepository, create_database
from app.routes.base import BaseBlueprint


class DashboardBlueprint(BaseBlueprint):
    """Provide the dashboard page."""

    def __init__(self) -> None:
        super().__init__("dashboard", "/dashboard")

    def register_routes(self) -> None:
        """Register dashboard HTML and JSON stats endpoints."""
        self.blueprint.add_url_rule("", view_func=self.dashboard)
        self.blueprint.add_url_rule("/data", view_func=self.dashboard_data)

    def _parse_date_param(self, name: str) -> date | None:
        raw = request.args.get(name)
        if not raw or not raw.strip():
            return None
        return date.fromisoformat(raw.strip())

    def _dashboard_context(self) -> tuple[dict[str, object] | None, int | None]:
        """Return (context, http_error) — context is None when error is set."""
        region = request.args.get("region")
        region = region.strip() if region and region.strip() else None
        try:
            start = self._parse_date_param("start")
            end = self._parse_date_param("end")
        except ValueError:
            return None, 400

        with create_database() as db:
            rules = RuleRepository(db)
            try:
                rules.load_from_csv()
            except Exception:
                pass
            regions = rules.get_regions()
            scans = ScanRepository(db)
            payload = build_dashboard_payload(scans, region=region, start=start, end=end)

        context: dict[str, object] = {
            "payload": payload,
            "regions": regions,
            "selected_region": region or "",
            "start": request.args.get("start") or "",
            "end": request.args.get("end") or "",
        }
        return context, None

    def dashboard(self) -> str | tuple[str, int]:
        """Render the dashboard with stats and chart (subsystem C)."""
        context, err = self._dashboard_context()
        if err == 400:
            return "Invalid date: use YYYY-MM-DD for start and end.", 400
        assert context is not None
        return render_template("dashboard.html", **context)

    def dashboard_data(self) -> Response:
        """Return the same payload as JSON for APIs or HT3 wiring checks."""
        context, err = self._dashboard_context()
        if err == 400:
            return jsonify({"error": "Invalid date: use YYYY-MM-DD for start and end."}), 400
        assert context is not None
        return jsonify(context["payload"])
