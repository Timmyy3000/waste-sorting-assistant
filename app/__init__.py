import os
import secrets

from flask import Flask, jsonify, render_template, request

from app.ai_services import AIServiceError
from app.analytics import AnalyticsError
from app.config import AppConfig
from app.db import DatabaseError, RuleRepository, create_database
from app.routes.api import ApiBlueprint
from app.routes.base import BaseBlueprint
from app.routes.dashboard import DashboardBlueprint
from app.routes.errors import UploadError, WebAppError
from app.routes.scan import ScanBlueprint, ScanWorkflow
from app.scan_reviews import ReviewRepository, csrf_token
from app.disposal import STREAMS


class AppFactory:
    """Build and configure a fresh Flask application."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config if config is not None else AppConfig()

    def create(self) -> Flask:
        """Create the app and register its route groups."""
        app = Flask(__name__)
        # Set SECRET_KEY in deployment so browser ownership survives restarts.
        app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
        app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
        self.config.configure_ai()
        app.config["WEB_INTEGRATED"] = True
        app.config["LOCAL_VISION_ENABLED"] = bool(os.getenv("LOCAL_VISION_MODEL_DIR"))
        app.config["APP_VERSION"] = "2026-11-07-confirmation-v7"
        app.config["MAX_CONTENT_LENGTH"] = self.config.upload_limit
        app.config["ALLOWED_TYPES"] = self.config.allowed_types
        app.config["DB_HOST"] = self.config.database_host
        app.config["DB_NAME"] = self.config.database_name
        app.config["DB_USER"] = self.config.database_user
        app.config["DB_PASSWORD"] = self.config.database_password

        @app.route("/")
        def index() -> str:
            return render_template("index.html", regions=ScanWorkflow().get_regions(),
                                   streams=STREAMS, csrf_token=csrf_token())

        with create_database() as database:
            RuleRepository(database).load_from_csv()
            ReviewRepository(database).reconcile_pending()

        route_groups: list[BaseBlueprint] = [
            ScanBlueprint(),
            DashboardBlueprint(),
            ApiBlueprint(),
        ]
        for group in route_groups:
            app.register_blueprint(group.blueprint)
        self._register_error_handlers(app)

        @app.after_request
        def identify_version(response):
            response.headers["X-App-Version"] = app.config["APP_VERSION"]
            response.headers["X-Vision-Backend"] = "offline" if app.config["LOCAL_VISION_ENABLED"] else "manual"
            if response.mimetype == "text/html":
                response.headers["Cache-Control"] = "no-store"
            return response

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
            app.logger.error("A database operation failed (%s)", type(error).__name__)
            return response_for(Exception("We could not access your scans. Please try again."), 503)

        @app.errorhandler(AnalyticsError)
        def handle_analytics_error(error: AnalyticsError):
            return response_for(error, 400)

        @app.errorhandler(WebAppError)
        def handle_web_error(error: WebAppError):
            return response_for(error, error.http_status)

        @app.errorhandler(404)
        def handle_not_found(error):
            return response_for(Exception("We couldn't find that page. Let's get you back to sorting."), 404)

        @app.errorhandler(413)
        def handle_too_large(error):
            return response_for(Exception("This upload is too large. Choose a photo under 5 MB."), 413)

        @app.errorhandler(500)
        def handle_unexpected_error(error):
            return response_for(Exception("Something went wrong. Please try again in a moment."), 500)


def create_app() -> Flask:
    """Build the Flask app. Tests call this to get a fresh app."""
    return AppFactory().create()
