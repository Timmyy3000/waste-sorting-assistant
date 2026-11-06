"""Upload routes and the shared web-to-service workflow."""

from datetime import datetime, timezone

from flask import current_app, render_template, request
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import BadRequest

from app.ai_services import AIService, AIUnavailableError
from app.db import RuleRepository, Scan, ScanRepository, create_database
from app.routes.base import BaseBlueprint


class ScanWorkflow:
    """Validate one upload and connect the AI, rules and scan repository."""

    def __init__(self, service: AIService | None = None) -> None:
        self._service = service if service is not None else AIService()

    def get_regions(self) -> list[str]:
        """Read supported regions from the rules repository."""
        with create_database() as database:
            return RuleRepository(database).get_regions()

    def submit(self, upload: FileStorage | None, region: str) -> dict:
        """Return a saved classification with its local disposal instructions."""
        region = region.strip()
        if upload is None or not upload.filename or not region:
            raise BadRequest("Choose a photo and region.")
        extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
        if extension not in current_app.config["ALLOWED_TYPES"]:
            raise BadRequest("Only JPEG and PNG files are allowed.")
        if region not in self.get_regions():
            raise BadRequest("Choose a region from the list so we can find its local rules.")
        image_bytes = upload.read(current_app.config["MAX_CONTENT_LENGTH"] + 1)
        if not image_bytes:
            raise BadRequest("The photo is empty. Please choose another file.")

        try:
            result = self._service.classify_upload(image_bytes, region)
        except (ValueError, TypeError, KeyError):
            raise AIUnavailableError("We could not interpret the AI response. Please try another photo.") from None
        with create_database() as database:
            rule = RuleRepository(database).get_rule(region, result["category"])
            scan = Scan(
                None, datetime.now(timezone.utc), region, result["category"],
                result["material"], result["confidence"],
            )
            result["scan_id"] = ScanRepository(database).save_scan(scan)
        result["bin"] = rule.bin
        result["instructions"] = rule.instructions
        return result


class ScanBlueprint(BaseBlueprint):
    """Provide the upload page and classification result."""

    def __init__(self) -> None:
        super().__init__("scan", "/scan")

    def register_routes(self) -> None:
        """Register the upload form and its POST handler."""
        self.blueprint.add_url_rule("", view_func=self.scan, methods=["GET", "POST"])

    def scan(self) -> str:
        """Render the upload form, or classify and save an uploaded item."""
        workflow = ScanWorkflow()
        if request.method == "GET":
            return render_template("scan.html", regions=workflow.get_regions())
        result = workflow.submit(request.files.get("photo"), request.form.get("region", ""))
        return render_template("result.html", result=result)
