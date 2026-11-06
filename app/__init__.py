from flask import Flask, jsonify, render_template, request

from app.ai_services import AIServiceError
from app.analytics import AnalyticsError
from app.config import AppConfig
from app.db import DatabaseError, RuleRepository, create_database
from app.routes.api import ApiBlueprint
from app.routes.base import BaseBlueprint
from app.routes.dashboard import DashboardBlueprint
from app.routes.errors import UploadError, WebAppError
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
        self._register_error_handlers(app)
        return app

    @staticmethod
    def _register_error_handlers(app: Flask) -> None:
        """Turn subsystem exceptions and HTTP errors into safe responses."""

        def response_for(error: Exception, status: int):
            message = str(error) or "The request could not be completed."
            if request.path.startswith("/api/"):
                return jsonify({"error": message}), status
            return render_template("error.html", message=message), status

        @app.errorhandler(AIServiceError)
        def handle_ai_error(error: AIServiceError):
            return response_for(error, getattr(error, "http_status", 500))

        @app.errorhandler(DatabaseError)
        def handle_database_error(error: DatabaseError):
            return response_for(error, 500)

        @app.errorhandler(AnalyticsError)
        def handle_analytics_error(error: AnalyticsError):
            return response_for(error, 400)

        @app.errorhandler(WebAppError)
        def handle_web_error(error: WebAppError):
            return response_for(error, error.http_status)

        @app.errorhandler(404)
        def handle_not_found(error):
            return response_for(error, 404)

        @app.errorhandler(413)
        def handle_too_large(error):
            return response_for(error, 413)


def create_app() -> Flask:
    """Build the Flask app. Tests call this to get a fresh app."""
    return AppFactory().create()
