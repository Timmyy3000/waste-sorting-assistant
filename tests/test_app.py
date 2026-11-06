from io import BytesIO

import pytest

from app import create_app
from app.ai_services import Classification
from app.config import AppConfig


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a Flask client with an isolated SQLite database."""
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    return create_app().test_client()


def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Waste Sorting Assistant" in response.data


def test_pages_and_stats_api_load(client):
    assert client.get("/scan").status_code == 200
    assert client.get("/dashboard").status_code == 200
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.get_json()["total_scans"] == 0


def test_scan_upload_uses_services_and_database(client, monkeypatch):
    """A valid upload is classified, saved and shown on the result page."""

    def fake_classify_upload(self, image_bytes, region):
        result = Classification("recyclable", "plastic bottle", 0.9)
        answer = result.to_dict()
        answer.update({"region": region, "tip": "Rinse the bottle."})
        return answer

    monkeypatch.setattr("app.routes.scan.AIService.classify_upload", fake_classify_upload)
    response = client.post(
        "/scan",
        data={
            "region": "Dortmund",
            "photo": (BytesIO(b"\x89PNG\r\n\x1a\nimage"), "bottle.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert b"plastic bottle" in response.data
    assert b"yellow bin" in response.data


def test_config_properties():
    config = AppConfig()
    config.upload_limit = 1024
    config.allowed_types = {"PNG"}
    assert config.upload_limit == 1024
    assert config.allowed_types == {"png"}
    assert create_app().config["MAX_CONTENT_LENGTH"] == 5 * 1024 * 1024


def test_pipeline_chains_without_consuming_source_early():
    from app.ai_services import SimulatedScanSource
    from app.analytics import RegionFilter
    from app.pipeline_runner import Pipeline

    source = SimulatedScanSource(count=10, seed=1)
    original = Pipeline(source)
    filtered = original | RegionFilter("Dortmund")
    assert source.produced == 0
    events = list(filtered)
    assert events
    assert all(event.region == "Dortmund" for event in events)
    assert source.produced == 10
