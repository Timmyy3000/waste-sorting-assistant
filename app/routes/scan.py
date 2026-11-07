"""Upload routes and the shared web-to-service workflow."""

from datetime import datetime, timezone

import secrets

from flask import current_app, redirect, render_template, request, session, url_for
from werkzeug.datastructures import FileStorage

from app.ai_services import AIService, AIUnavailableError
from app.db import RuleRepository, Scan, ScanRepository, create_database
from app.disposal import CATEGORY, STREAMS, guidance, suggestion
from app.image_uploads import normalise
from app.item_text import agrees_with_photo, identify
from app.routes.base import BaseBlueprint
from app.routes.errors import UploadError
from app.scan_reviews import ReviewRepository, csrf_token, owner_hash


class ScanWorkflow:
    """Validate one upload and connect the AI, rules and scan repository."""

    def __init__(self, service: AIService | None = None) -> None:
        self._service = service if service is not None else AIService()

    def get_regions(self) -> list[str]:
        """Read supported regions from the rules repository."""
        with create_database() as database:
            return RuleRepository(database).get_regions()

    def submit(self, upload: FileStorage | None, region: str, description: str = "") -> dict:
        """Save a text, photo or combined unverified suggestion for confirmation."""
        region = region.strip() if isinstance(region, str) else ""
        description = description.strip() if isinstance(description, str) else ""
        has_photo = upload is not None and bool(upload.filename)
        if not region or (not has_photo and not description):
            raise UploadError("Choose a city and provide a photo and/or item description.")
        if len(description) > 120 or any(ord(char) < 32 for char in description):
            raise UploadError("Describe the item in at most 120 characters, without control characters.")
        if region not in self.get_regions():
            raise UploadError("Choose a region from the list so we can find its local rules.")
        if has_photo:
            extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
            if extension not in current_app.config["ALLOWED_TYPES"]:
                raise UploadError("Choose a supported photo (JPG, PNG, WebP, GIF, BMP, TIFF, AVIF or HEIC).")
            image_bytes = upload.read(current_app.config["MAX_CONTENT_LENGTH"] + 1)
            if not image_bytes:
                raise UploadError("The photo is empty. Please choose another file.")
            image_bytes = normalise(image_bytes)
            try:
                result = self._service.classify_upload(image_bytes, region)
            except (ValueError, TypeError, KeyError):
                raise AIUnavailableError("We could not interpret the AI response. Please try another photo.") from None
            if description:
                photo_material = result["material"]
                text_item = identify(description)
                if (result["category"] != "unknown" and text_item.category != "unknown"
                        and result["category"] == text_item.category
                        and agrees_with_photo(description, photo_material)):
                    result["ai_material"] = (
                        f"photo only supports broad item: {photo_material}"
                        if text_item.material != photo_material
                        else f"photo + text agree: {photo_material}"
                    )
                else:
                    result["category"] = "unknown"
                    result["material"] = description
                    result["confidence"] = 0.0
                    result["ai_material"] = f"photo could not verify '{description}' (photo suggested: {photo_material})"
        else:
            item = identify(description)
            result = item.to_dict()
            result["material"] = item.material
            result["ai_material"] = f"text only: {description}"
            result["region"] = region
        stream = suggestion(result["category"], result["material"])
        result["ai_category"] = result["category"]
        result.setdefault("ai_material", result["material"])
        # A model-only suggestion is not enough to recommend a disposal bin.
        guide = guidance(region, "unknown")
        with create_database() as database:
            scan = Scan(
                None, datetime.now(timezone.utc), region, "unknown",
                result["material"], result["confidence"],
            )
            result["scan_id"] = ScanRepository(database).save_scan(scan)
            ReviewRepository(database).create(result["scan_id"], owner_hash(), stream, result)
        # A suggestion is not a saved sorting choice or a dashboard success.
        result["category"] = "unknown"
        result["stream"] = stream
        result["stream_label"] = STREAMS[stream]
        result["status"] = "unresolved" if stream == "unknown" else "suggested"
        result["needs_confirmation"] = True
        result["version"] = 0
        result["bin"] = guide.bin
        result["instructions"] = guide.instructions
        result["source"] = guide.source
        result["tip"] = "Review the item and verify the municipal guidance before disposal."
        result["csrf_token"] = csrf_token()
        return result

    def owned_result(self, scan_id: int) -> dict:
        with create_database() as database:
            review = ReviewRepository(database).get_owned(scan_id, owner_hash())
        if review is None:
            raise UploadError("This scan is not available in your browser session.")
        guide = guidance(review["region"],
                         "unknown" if review["status"] == "suggested" else review["stream"])
        return {
            "scan_id": scan_id, "region": review["region"], "category": review["category"],
            "stream": review["stream"], "stream_label": STREAMS[review["stream"]],
            "material": review["material"], "confidence": review["confidence"],
            "ai_category": review["ai_category"], "ai_material": review["ai_material"],
            "status": review["status"], "version": review["version"],
            "needs_confirmation": review["status"] in ("unresolved", "suggested"),
            "bin": guide.bin, "instructions": guide.instructions, "source": guide.source,
            "tip": "Check the linked municipal guide before disposal.", "csrf_token": csrf_token(),
        }

    def manual(self, region: str, stream: str, material: str, token: str) -> dict:
        """Allow useful sorting even when the configured vision model is offline."""
        if not isinstance(token, str) or not token or not secrets.compare_digest(token, session.get("scan_csrf", "")):
            raise UploadError("The form expired. Reload and try again.")
        region = region.strip() if isinstance(region, str) else ""
        if region not in self.get_regions():
            raise UploadError("Choose a supported city.")
        if stream not in STREAMS or stream == "unknown":
            raise UploadError("Choose a disposal route after checking the item.")
        material = material.strip() if isinstance(material, str) else ""
        if not 1 <= len(material) <= 120:
            raise UploadError("Describe the item in 1–120 characters.")
        with create_database() as database:
            scan = Scan(None, datetime.now(timezone.utc), region, CATEGORY[stream], material, 0)
            scan_id = ScanRepository(database).save_scan(scan)
            ReviewRepository(database).create(scan_id, owner_hash(), stream, {
                "category": "unknown", "material": "no AI used", "confidence": 0,
            }, status="confirmed")
        return self.owned_result(scan_id)

    def correct(self, scan_id: int, stream: str, material: str, version: int, token: str) -> dict:
        if not isinstance(token, str) or not secrets.compare_digest(token, session.get("scan_csrf", "")) or not token:
            raise UploadError("The correction form expired. Reload the page and try again.")
        with create_database() as database:
            ReviewRepository(database).correct(scan_id, owner_hash(), stream, material, version)
        return self.owned_result(scan_id)


class ScanBlueprint(BaseBlueprint):
    """Provide the upload page and classification result."""

    def __init__(self) -> None:
        super().__init__("scan", "/scan")

    def register_routes(self) -> None:
        """Register the upload form and its POST handler."""
        self.blueprint.add_url_rule("", view_func=self.scan, methods=["GET", "POST"])
        self.blueprint.add_url_rule("/<int:scan_id>", view_func=self.result_page)
        self.blueprint.add_url_rule("/<int:scan_id>/correct", view_func=self.correct_page, methods=["POST"])
        self.blueprint.add_url_rule("/manual", view_func=self.manual_page, methods=["POST"])

    def scan(self) -> str:
        """Render the upload form, or classify and save an uploaded item."""
        workflow = ScanWorkflow()
        if request.method == "GET":
            return render_template("scan.html", regions=workflow.get_regions(),
                                   streams=STREAMS, csrf_token=csrf_token())
        result = workflow.submit(request.files.get("photo"), request.form.get("region", ""),
                                 request.form.get("description", ""))
        return render_template("result.html", result=result, streams=STREAMS)

    def result_page(self, scan_id: int) -> str:
        return render_template("result.html", result=ScanWorkflow().owned_result(scan_id), streams=STREAMS)

    def correct_page(self, scan_id: int):
        try:
            version = int(request.form.get("version", ""))
        except ValueError:
            raise UploadError("Reload the result before correcting it.") from None
        ScanWorkflow().correct(scan_id, request.form.get("stream", ""),
                               request.form.get("material", ""), version,
                               request.form.get("csrf_token", ""))
        return redirect(url_for("scan.result_page", scan_id=scan_id), code=303)

    def manual_page(self):
        result = ScanWorkflow().manual(request.form.get("region", ""),
            request.form.get("stream", ""), request.form.get("material", ""),
            request.form.get("csrf_token", ""))
        return redirect(url_for("scan.result_page", scan_id=result["scan_id"]), code=303)
