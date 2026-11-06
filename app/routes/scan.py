"""Routes for scanning waste."""

from flask import render_template

from app.routes.base import BaseBlueprint


class ScanBlueprint(BaseBlueprint):
    """Provide the scan page."""

    def __init__(self) -> None:
        super().__init__("scan", "/scan")

    def register_routes(self) -> None:
        """Register the placeholder scan page."""
        self.blueprint.add_url_rule("", view_func=self.scan)

    def scan(self) -> str:
        """Render the scan page."""
        return render_template("scan.html")
