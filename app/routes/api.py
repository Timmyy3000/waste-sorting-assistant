"""JSON endpoints for classification and dashboard statistics."""

from datetime import date

from flask import Response, jsonify, request

from app.ai_services import AIService
from app.analytics import build_dashboard_payload
from app.db import ScanRepository, create_database
from app.routes.base import BaseBlueprint


class ApiBlueprint(BaseBlueprint):
    """Provide the application's JSON API."""

    def __init__(self) -> None:
        super().__init__("api", "/api")

    def register_routes(self) -> None:
        """Register statistics and classification endpoints."""
        self.blueprint.add_url_rule("/stats", view_func=self.stats)
        self.blueprint.add_url_rule("/classify", view_func=self.classify, methods=["POST"])

    def stats(self) -> Response:
        """Return dashboard statistics as JSON."""
        region = request.args.get("region") or None
        try:
            start = date.fromisoformat(request.args["start"]) if request.args.get("start") else None
            end = date.fromisoformat(request.args["end"]) if request.args.get("end") else None
        except ValueError:
            return jsonify({"error": "Dates must use YYYY-MM-DD."}), 400
        with create_database() as database:
            payload = build_dashboard_payload(
                ScanRepository(database), region=region, start=start, end=end
            )
        return jsonify(payload)

    def classify(self) -> Response:
        """Classify an uploaded photo and return the result as JSON."""
        upload = request.files.get("photo")
        region = request.form.get("region", "").strip()
        if upload is None or not upload.filename or not region:
            return jsonify({"error": "Choose a photo and region."}), 400
        return jsonify(AIService().classify_upload(upload.read(), region))
