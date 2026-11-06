"""JSON endpoints using the same workflow as the browser interface."""

from flask import Response, jsonify, request

from app.routes.base import BaseBlueprint
from app.routes.dashboard import dashboard_payload
from app.routes.scan import ScanWorkflow


class ApiBlueprint(BaseBlueprint):
    """Expose server-side classification and statistics as JSON."""

    def __init__(self) -> None:
        super().__init__("api", "/api")

    def register_routes(self) -> None:
        """Register the public API routes."""
        self.blueprint.add_url_rule("/stats", view_func=self.stats)
        self.blueprint.add_url_rule("/classify", view_func=self.classify, methods=["POST"])

    def stats(self) -> Response:
        """Return filtered statistics without exposing server credentials."""
        return jsonify(dashboard_payload())

    def classify(self) -> Response:
        """Classify and save an upload, then return the local rule and tip."""
        result = ScanWorkflow().submit(request.files.get("photo"), request.form.get("region", ""))
        return jsonify(result)
