"""Routes for classifying and saving waste scans."""

from datetime import datetime

from flask import current_app, render_template, request

from app.ai_services import AIService
from app.db import RuleRepository, Scan, ScanRepository, create_database
from app.routes.base import BaseBlueprint


class ScanBlueprint(BaseBlueprint):
    """Provide the scan page."""

    def __init__(self) -> None:
        super().__init__("scan", "/scan")

    def register_routes(self) -> None:
        """Register the upload form for GET and POST requests."""
        self.blueprint.add_url_rule("", view_func=self.scan, methods=["GET", "POST"])

    def scan(self) -> str | tuple[str, int]:
        """Show the form or classify, save and display one uploaded image."""
        if request.method == "GET":
            return render_template("scan.html")

        upload = request.files.get("photo")
        region = request.form.get("region", "").strip()
        if upload is None or not upload.filename or not region:
            return render_template("error.html", message="Choose a photo and region."), 400

        extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
        if extension not in current_app.config["ALLOWED_TYPES"]:
            return render_template("error.html", message="Only JPEG and PNG files are allowed."), 400

        result = AIService().classify_upload(upload.read(), region)
        with create_database() as database:
            scan = Scan(
                None,
                datetime.now(),
                region,
                result["category"],
                result["material"],
                result["confidence"],
            )
            scan_id = ScanRepository(database).save_scan(scan)
            rule = RuleRepository(database).get_rule(region, result["category"])

        return render_template("result.html", result=result, rule=rule, scan_id=scan_id)
