"""Routes for the recycling dashboard."""

from flask import render_template

from app.routes.base import BaseBlueprint


class DashboardBlueprint(BaseBlueprint):
    """Provide the dashboard page."""

    def __init__(self) -> None:
        super().__init__("dashboard", "/dashboard")

    def register_routes(self) -> None:
        """Register the placeholder dashboard page."""
        self.blueprint.add_url_rule("", view_func=self.dashboard)

    def dashboard(self) -> str:
        """Render the dashboard page."""
        return render_template("dashboard.html")
