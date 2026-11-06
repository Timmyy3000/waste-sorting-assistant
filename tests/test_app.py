"""Flask tests for subsystem D."""

from io import BytesIO

import pytest

from app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Return a test client with an isolated SQLite database."""
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_home_page_loads(client):
    """Black-box check: the home page is available."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Waste Sorting Assistant" in response.data


def test_text_upload_shows_friendly_error(client):
    """A non-image filename is rejected before calling the AI service."""
    response = client.post(
        "/scan",
        data={"region": "Dortmund", "photo": (BytesIO(b"text"), "notes.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert b"Only JPEG and PNG files are allowed" in response.data


def test_stats_api_returns_json(client):
    """The dashboard API returns JSON-friendly empty statistics."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.get_json()["total_scans"] == 0
