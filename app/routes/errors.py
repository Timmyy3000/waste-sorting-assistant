"""Exceptions raised by the web application layer."""


class WebAppError(Exception):
    """Base class for errors owned by the Flask web layer."""

    http_status = 400


class UploadError(WebAppError):
    """The upload form is missing data or contains an unsupported file."""
