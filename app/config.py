"""Configuration for the web application."""

import os


class AppConfig:
    """Store upload and database settings for the application."""

    def __init__(self) -> None:
        self._upload_limit = 5 * 1024 * 1024
        self._allowed_types = {"jpg", "jpeg", "png"}
        self._database_host = os.getenv("DB_HOST", "")
        self._database_name = os.getenv("DB_NAME", "waste_sorting")
        self._database_user = os.getenv("DB_USER", "")
        self._database_password = os.getenv("DB_PASSWORD", "")

    @property
    def upload_limit(self) -> int:
        """Return the maximum upload size in bytes."""
        return self._upload_limit

    @upload_limit.setter
    def upload_limit(self, value: int) -> None:
        if value <= 0:
            raise ValueError("Upload limit must be positive")
        self._upload_limit = value

    @property
    def allowed_types(self) -> set[str]:
        """Return the allowed filename extensions."""
        return self._allowed_types.copy()

    @allowed_types.setter
    def allowed_types(self, value: set[str]) -> None:
        self._allowed_types = {extension.lower() for extension in value}

    @property
    def database_host(self) -> str:
        """Return the database host."""
        return self._database_host

    @database_host.setter
    def database_host(self, value: str) -> None:
        self._database_host = value

    @property
    def database_name(self) -> str:
        """Return the database name."""
        return self._database_name

    @database_name.setter
    def database_name(self, value: str) -> None:
        self._database_name = value

    @property
    def database_user(self) -> str:
        """Return the database user."""
        return self._database_user

    @database_user.setter
    def database_user(self, value: str) -> None:
        self._database_user = value

    @property
    def database_password(self) -> str:
        """Return the database password."""
        return self._database_password

    @database_password.setter
    def database_password(self, value: str) -> None:
        self._database_password = value
