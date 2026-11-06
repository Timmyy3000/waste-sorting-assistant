"""Flask tests for subsystem D."""

from io import BytesIO

import pytest
from PIL import Image

from app import create_app


def photo(format="PNG"):
    output = BytesIO()
    Image.new("RGB", (64, 64), "#e2cfa0").save(output, format=format)
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Return a test client with an isolated SQLite database."""
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-server-secret-not-for-browsers")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_home_page_loads(client):
    """Black-box check: the home page is available."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Waste Sorting Assistant" in response.data
    assert b'name="photo"' in response.data
    assert b'name="region"' in response.data
    assert b"css/app.css" in response.data
    assert b"test-server-secret-not-for-browsers" not in response.data
    assert b"Bottles and Pfand" in response.data
    assert b"Illustration of a Pfand bottle return machine" in response.data
    assert b"Altglas" in response.data
    assert response.headers["X-App-Version"] == "2026-11-06-sorting-v2"


def test_text_upload_shows_friendly_error(client):
    """A non-image filename is rejected before calling the AI service."""
    response = client.post(
        "/scan",
        data={"region": "Dortmund", "photo": (BytesIO(b"text"), "notes.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert b"Choose a supported photo" in response.data


def test_stats_api_returns_json(client):
    """The dashboard API returns JSON-friendly empty statistics."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.get_json()["total_scans"] == 0


def test_successful_upload_is_saved_and_shown(client, monkeypatch):
    """Mock only the external service; use the real database and templates."""
    from app.ai_services import AIService

    def classify(self, image_bytes: bytes, region: str) -> dict:
        assert image_bytes.startswith(b"\xff\xd8\xff")  # Normalised for vision.
        return {
            "category": "recyclable", "material": "plastic bottle", "confidence": 0.92,
            "needs_confirmation": False, "region": region, "tip": "Empty the bottle first.",
        }

    monkeypatch.setattr(AIService, "classify_upload", classify)
    response = client.post("/scan", data={
        "region": "Dortmund", "photo": (BytesIO(photo()), "bottle.png"),
    })
    assert response.status_code == 200
    assert b"plastic bottle" in response.data
    assert b"Check the city" in response.data
    payload = client.get("/api/stats").get_json()
    assert payload["total_scans"] == 1
    assert payload["category_counts"]["unknown"] == 1
    assert payload["recycling_rate"] == 0.0


@pytest.mark.parametrize("path", ["/scan", "/api/classify"])
def test_unknown_region_does_not_call_provider(client, monkeypatch, path):
    from app.ai_services import AIService

    def should_not_call(self, image_bytes: bytes, region: str) -> dict:
        pytest.fail("Invalid requests must be rejected before calling the provider")

    monkeypatch.setattr(AIService, "classify_upload", should_not_call)
    response = client.post(path, data={
        "region": "Not a supported city", "photo": (BytesIO(b"image"), "bottle.png"),
    })
    assert response.status_code == 400


@pytest.mark.parametrize("path", ["/scan", "/api/classify"])
def test_missing_upload_is_rejected(client, path):
    assert client.post(path, data={"region": "Dortmund"}).status_code == 400


def test_api_upload_uses_the_same_saved_workflow(client, monkeypatch):
    from app.ai_services import AIService

    def classify(self, image_bytes: bytes, region: str) -> dict:
        return {
            "category": "unknown", "material": "mixed item", "confidence": 0.4,
            "needs_confirmation": True, "region": region, "tip": "Ask the recycling centre.",
        }

    monkeypatch.setattr(AIService, "classify_upload", classify)
    response = client.post("/api/classify", data={
        "region": "Dortmund", "photo": (BytesIO(photo()), "item.png"),
    })
    assert response.status_code == 200
    assert response.get_json()["scan_id"] > 0
    assert response.get_json()["bin"] == "Check the city's Abfall-ABC"
    assert "test-server-secret-not-for-browsers" not in response.get_data(as_text=True)


def test_unknown_scans_are_excluded_from_recycling_rate(client):
    from datetime import datetime
    from app.db import Scan, ScanRepository, create_database

    with create_database() as database:
        repository = ScanRepository(database)
        for category in ("recyclable", "compostable", "landfill", "unknown"):
            repository.save_scan(Scan(None, datetime(2026, 11, 6), "Dortmund", category, "item", 0.7))
    payload = client.get("/api/stats").get_json()
    assert payload["total_scans"] == 4
    assert payload["recycling_rate"] == pytest.approx(2 / 3, abs=0.0001)


@pytest.mark.parametrize("query", ["start=wrong", "start=2026-11-07&end=2026-11-01"])
def test_invalid_filters_return_json_errors(client, query):
    response = client.get("/api/stats?" + query)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_provider_failure_is_friendly(client, monkeypatch):
    from app.ai_services import AIService, AIUnavailableError

    def unavailable(self, image_bytes: bytes, region: str) -> dict:
        raise AIUnavailableError("The classification service is temporarily unavailable.")

    monkeypatch.setattr(AIService, "classify_upload", unavailable)
    response = client.post("/scan", data={
        "region": "Dortmund", "photo": (BytesIO(photo()), "item.png"),
    })
    assert response.status_code == 503
    assert b"temporarily unavailable" in response.data
    assert b"Traceback" not in response.data


@pytest.mark.parametrize("path", ["/scan", "/api/classify"])
def test_unverified_provider_never_guesses_a_bin(client, monkeypatch, path):
    from app.ai_services import AIClient

    monkeypatch.setenv("OPENAI_BASE_URL", "https://chat.kiconnect.nrw/api/v1")

    def no_provider_call(*args, **kwargs):
        pytest.fail("Unverified provider must not receive a classification request")

    monkeypatch.setattr(AIClient, "call_vision", no_provider_call)
    response = client.post(path, data={
        "region": "Dortmund", "photo": (BytesIO(photo()), "item.png"),
    })
    assert response.status_code == 200
    if path == "/scan":
        assert b"Identification is unavailable" in response.data
        assert b"Not verified" in response.data
        assert b"<h2>Restm" not in response.data
    else:
        result = response.get_json()
        assert result["category"] == "unknown"
        assert result["material"] == "unverified item"
        assert result["confidence"] == 0
        assert result["needs_confirmation"] is True
        assert result["bin"] == "Check the city's Abfall-ABC"
    assert client.get("/api/stats").get_json()["category_counts"]["unknown"] == 1


def test_blank_ai_material_becomes_unknown_instead_of_database_error(client, monkeypatch):
    from app.ai_services import AIClient

    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.org/v1")
    monkeypatch.setattr(AIClient, "call_vision", lambda *args: '{"category":"landfill","material":"  ","confidence":0.99}')
    monkeypatch.setattr(AIClient, "call_text", lambda *args: "Consult local rules.")
    response = client.post("/api/classify", data={
        "region": "Dortmund", "photo": (BytesIO(photo()), "blank.png"),
    })
    assert response.status_code == 200
    assert response.get_json()["category"] == "unknown"
    assert response.get_json()["material"] == "unidentified item"
    assert response.get_json()["bin"] == "Check the city's Abfall-ABC"


def test_german_routes_and_ambiguous_bottles():
    from app.disposal import guidance, suggestion

    assert guidance("Berlin", "bio").bin == "Biotonne"
    assert "Papiertonne" in guidance("Dortmund", "paper").bin
    assert "Wertstofftonne" in guidance("Berlin", "packaging").bin
    assert "2026" in guidance("Munich", "packaging").instructions
    assert "Altglas" in guidance("Munich", "glass").bin
    assert "Pfand" in guidance("Berlin", "deposit").bin
    assert "vehicle" in guidance("Dortmund", "vehicle").bin
    assert suggestion("recyclable", "plastic bottle") == "unknown"
    assert suggestion("recyclable", "battery") == "unknown"
    assert suggestion("compostable", "banana peel") == "bio"


def test_correction_requires_owner_and_csrf_updates_stats_and_audit(client, monkeypatch):
    from app.ai_services import AIService
    from app.db import create_database

    monkeypatch.setattr(AIService, "classify_upload", lambda self, image, region: {
        "category": "unknown", "material": "unverified item", "confidence": 0,
        "needs_confirmation": True, "region": region, "tip": "Check city guidance.",
    })
    upload = client.post("/api/classify", data={
        "region": "Berlin", "photo": (BytesIO(photo()), "item.png"),
    }).get_json()
    scan_id = upload["scan_id"]
    endpoint = f"/api/scans/{scan_id}/correct"
    body = {"stream": "paper", "material": "cardboard", "version": 0}
    other = client.application.test_client()
    assert other.post(endpoint, json=body, headers={"X-CSRF-Token": upload["csrf_token"]}).status_code == 400
    assert client.post(endpoint, json=body).status_code == 400
    response = client.post(endpoint, json=body, headers={"X-CSRF-Token": upload["csrf_token"]})
    assert response.status_code == 200
    assert response.get_json()["status"] == "corrected"
    assert response.get_json()["bin"] == "Papiertonne / Blaue Tonne"
    assert client.get("/api/stats").get_json()["stream_counts"]["paper"] == 1
    assert client.get("/api/stats").get_json()["corrected_scans"] == 1
    assert b"Review / correct" in client.get("/dashboard").data
    assert b"Review / correct" not in other.get("/dashboard").data
    assert client.post(endpoint, json=body, headers={"X-CSRF-Token": upload["csrf_token"]}).status_code == 400
    with create_database() as database:
        changes = database.query("SELECT * FROM scan_corrections WHERE scan_id = ?", (scan_id,))
    assert len(changes) == 1
    assert changes[0]["old_stream"] == "unknown"
    assert changes[0]["new_stream"] == "paper"


def test_form_correction_and_invalid_stream(client, monkeypatch):
    from app.ai_services import AIService

    monkeypatch.setattr(AIService, "classify_upload", lambda self, image, region: {
        "category": "unknown", "material": "unverified item", "confidence": 0, "region": region,
    })
    client.post("/scan", data={
        "region": "Dortmund", "photo": (BytesIO(photo()), "item.png"),
    })
    with client.session_transaction() as sess:
        token = sess["scan_csrf"]
    data = {"material": "empty tin", "stream": "invalid", "version": 0, "csrf_token": token}
    assert client.post("/scan/1/correct", data=data).status_code == 400
    data["stream"] = "packaging"
    response = client.post("/scan/1/correct", data=data)
    assert response.status_code == 303
    assert b"Wertstofftonne" in client.get(response.headers["Location"]).data


def test_manual_sort_works_without_vision_or_photo(client, monkeypatch):
    from app.ai_services import AIService

    monkeypatch.setattr(AIService, "classify_upload", lambda *args: pytest.fail("Manual sort must not call AI"))
    assert b"Sort without a photo" in client.get("/").data
    with client.session_transaction() as sess:
        token = sess["scan_csrf"]
    assert client.post("/scan/manual", data={
        "region": "Berlin", "stream": "bio", "material": "banana peel",
    }).status_code == 400
    response = client.post("/scan/manual", data={
        "region": "Berlin", "stream": "bio", "material": "banana peel", "csrf_token": token,
    })
    assert response.status_code == 303
    result = client.get(response.headers["Location"])
    assert b"Biotonne" in result.data
    assert b"Confirmed" in result.data
    assert client.get("/api/stats").get_json()["stream_counts"]["bio"] == 1


def test_manual_special_collection_is_not_counted_as_unresolved(client):
    client.get("/")
    with client.session_transaction() as sess:
        token = sess["scan_csrf"]
    response = client.post("/scan/manual", data={
        "region": "Dortmund", "stream": "vehicle", "material": "old car",
        "csrf_token": token,
    })
    assert response.status_code == 303
    assert b"Authorised vehicle dismantler" in client.get(response.headers["Location"]).data
    stats = client.get("/api/stats").get_json()
    assert stats["stream_counts"]["vehicle"] == 1
    assert stats["unresolved_scans"] == 0


def test_ai_suggestion_shows_no_bin_until_confirmed(client, monkeypatch):
    from app.ai_services import AIService

    monkeypatch.setattr(AIService, "classify_upload", lambda self, data, region: {
        "category": "compostable", "material": "banana peel", "confidence": 0.98,
        "region": region, "tip": "Never use this as verified advice.",
    })
    first = client.post("/api/classify", data={
        "region": "Berlin", "photo": (BytesIO(photo()), "banana.png"),
    }).get_json()
    assert first["stream"] == "bio"
    assert first["status"] == "suggested"
    assert first["needs_confirmation"] is True
    assert first["bin"] == "Check the city's Abfall-ABC"
    page = client.get(f"/scan/{first['scan_id']}")
    assert b"Wrong result? Correct it" in page.data
    assert b"No bin recommendation" in page.data
    confirmed = client.post(f"/api/scans/{first['scan_id']}/correct", json={
        "stream": "bio", "material": "banana peel", "version": 0,
    }, headers={"X-CSRF-Token": first["csrf_token"]})
    assert confirmed.status_code == 200
    assert confirmed.get_json()["status"] == "confirmed"
    assert confirmed.get_json()["bin"] == "Biotonne"


def test_existing_sqlite_scans_survive_additive_schema(tmp_path, monkeypatch):
    import sqlite3
    from app.db import SCHEMA_PATH

    path = tmp_path / "previous-version.db"
    connection = sqlite3.connect(path)
    original = SCHEMA_PATH.read_text(encoding="utf-8").split("-- Additive tables")[0]
    connection.executescript(original)
    connection.execute(
        "INSERT INTO scans (timestamp, region, category, material, confidence) VALUES (?, ?, ?, ?, ?)",
        ("2026-11-06T10:00:00", "Berlin", "recyclable", "old paper", 0.8),
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.delenv("DB_HOST", raising=False)
    app = create_app()
    app.config["TESTING"] = True
    response = app.test_client().get("/api/stats")
    assert response.status_code == 200
    assert response.get_json()["total_scans"] == 1
    assert response.get_json()["stream_counts"]["paper"] == 0  # Do not invent old detail.


def test_upload_limit_and_404_are_friendly(client):
    client.application.config["MAX_CONTENT_LENGTH"] = 100
    assert client.post("/api/classify", data={"photo": (BytesIO(b"x" * 200), "large.png")}).status_code == 413
    assert client.get("/not-a-page").status_code == 404


@pytest.mark.parametrize("path", [
    "/scan", "/dashboard", "/static/css/app.css", "/static/css/polish.css",
    "/static/js/app.js", "/static/favicon.svg",
])
def test_pages_and_assets_are_available(client, path):
    assert client.get(path).status_code == 200


def test_configuration_loads_key_from_private_file(tmp_path, monkeypatch):
    import os
    from app.config import AppConfig

    secret_file = tmp_path / "test-key.txt"
    secret_file.write_text("a-private-test-key", encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY_FILE", str(secret_file))
    AppConfig().configure_ai()
    assert os.environ["OPENAI_API_KEY"] == "a-private-test-key"


def test_existing_environment_key_takes_precedence(monkeypatch):
    import os
    from app.config import AppConfig

    monkeypatch.setenv("OPENAI_API_KEY", "already-configured-test-key")
    monkeypatch.setenv("OPENAI_API_KEY_FILE", "a-file-that-does-not-exist")
    AppConfig().configure_ai()
    assert os.environ["OPENAI_API_KEY"] == "already-configured-test-key"


def test_pipeline_is_lazy_and_uses_real_team_processors():
    from app.ai_services import SimulatedScanSource
    from app.analytics import CategoryTally, RegionFilter
    from app.db import Database, DbSink, ScanRepository
    from app.pipeline_runner import Pipeline

    with Database() as database:
        repository = ScanRepository(database)
        source = SimulatedScanSource(count=10, seed=1)
        tally = CategoryTally()
        sink = DbSink(repository)
        original = Pipeline(source)
        filtered = original | RegionFilter("Dortmund") | tally | sink
        assert filtered is not original
        assert source.produced == 0
        events = list(filtered.run())
        assert events and all(event.region == "Dortmund" for event in events)
        assert sink.saved == len(events) == len(repository.get_scans())
        assert sum(tally.counts.values()) == len(events)
