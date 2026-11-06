"""Common interface for the application's blueprints."""

from abc import ABC, abstractmethod

from flask import Blueprint


class BaseBlueprint(ABC):
    """Give each group of routes a name and a Flask blueprint."""

    def __init__(self, name: str, url_prefix: str) -> None:
        self._blueprint = Blueprint(name, __name__, url_prefix=url_prefix)
        self.register_routes()

    @property
    def blueprint(self) -> Blueprint:
        """Return the Flask blueprint for registration."""
        return self._blueprint

    @abstractmethod
    def register_routes(self) -> None:
        """Add the routes belonging to this blueprint."""
