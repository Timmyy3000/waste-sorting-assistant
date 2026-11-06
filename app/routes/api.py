"""JSON endpoints using the same workflow as the browser interface."""

from flask import Response, jsonify, request

from app.routes.base import BaseBlueprint
from app.routes.dashboard import dashboard_payload
from app.routes.scan import ScanWorkflow
from app.routes.errors import UploadError


class ApiBlueprint(BaseBlueprint):
    """Expose server-side classification and statistics as JSON."""

    def __init__(self) -> None:
        super().__init__("api", "/api")

    def register_routes(self) -> None:
        """Register the public API routes."""
        self.blueprint.add_url_rule("/stats", view_func=self.stats)
        self.blueprint.add_url_rule("/classify", view_func=self.classify, methods=["POST"])
        self.blueprint.add_url_rule("/scans/<int:scan_id>/correct", view_func=self.correct, methods=["POST"])

    def stats(self) -> Response:
        """Return filtered statistics without exposing server credentials."""
        return jsonify(dashboard_payload())

    def classify(self) -> Response:
        """Classify and save an upload, then return the local rule and tip."""
        result = ScanWorkflow().submit(request.files.get("photo"), request.form.get("region", ""))
        return jsonify(result)

    def correct(self, scan_id: int) -> Response:
        """Correct an owned scan; the CSRF token comes from /api/classify."""
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise UploadError("Send a JSON correction.")
        try:
            version = int(data.get("version"))
        except (ValueError, TypeError):
            raise UploadError("Provide the current result version.") from None
        return jsonify(ScanWorkflow().correct(scan_id, data.get("stream", ""),
                                               data.get("material", ""), version,
                                               request.headers.get("X-CSRF-Token", "")))
