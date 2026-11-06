from flask import Flask, render_template

from app.config import AppConfig
from app.db import RuleRepository, create_database
from app.routes.api import ApiBlueprint
from app.routes.base import BaseBlueprint
from app.routes.dashboard import DashboardBlueprint
from app.routes.scan import ScanBlueprint


class AppFactory:
    """Build and configure a fresh Flask application."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config if config is not None else AppConfig()

    def create(self) -> Flask:
        """Create the app and register its route groups."""
        app = Flask(__name__)
        app.config["MAX_CONTENT_LENGTH"] = self.config.upload_limit
        app.config["ALLOWED_TYPES"] = self.config.allowed_types
        app.config["DB_HOST"] = self.config.database_host
        app.config["DB_NAME"] = self.config.database_name
        app.config["DB_USER"] = self.config.database_user
        app.config["DB_PASSWORD"] = self.config.database_password

        @app.route("/")
        def index() -> str:
            return render_template("index.html")

        with create_database() as database:
            RuleRepository(database).load_from_csv()

        route_groups: list[BaseBlueprint] = [
            ScanBlueprint(),
            DashboardBlueprint(),
            ApiBlueprint(),
        ]
        for group in route_groups:
            app.register_blueprint(group.blueprint)
        return app


def create_app() -> Flask:
    """Build the Flask app. Tests call this to get a fresh app."""
    return AppFactory().create()
