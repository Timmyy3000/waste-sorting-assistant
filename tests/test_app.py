"""Flask tests for subsystem D."""

from io import BytesIO

import pytest
from PIL import Image

from app import create_app


def photo(format="PNG"):
    output = BytesIO()
    Image.new("RGB", (64, 64), "#e2cfa0").save(output, format=format)
    return output.getvalue()


def other_photo():
    output = BytesIO()
    Image.new("RGB", (64, 64), "#6cba4d").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Return a test client with an isolated SQLite database."""
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OPENAI_API_KEY", "test-server-secret-not-for-browsers")
    monkeypatch.setenv("LOCAL_VISION_MODEL_DIR", "")
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
    assert response.headers["X-App-Version"] == "2026-11-07-confirmation-v7"


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
        assert b"Unverified suggestion" in response.data
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
    assert response.headers["Location"].endswith("/dashboard")
    assert b"Confirmation saved." in client.get(response.headers["Location"]).data
    assert b"Wertstofftonne" in client.get("/scan/1").data


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
    assert client.get("/api/stats").get_json()["stream_counts"]["bio"] == 0
    page = client.get(f"/scan/{first['scan_id']}")
    assert b"Confirm a route or correct this result" in page.data
    assert b"No bin recommendation" in page.data
    confirmed = client.post(f"/api/scans/{first['scan_id']}/correct", json={
        "stream": "bio", "material": "banana peel", "version": 0,
    }, headers={"X-CSRF-Token": first["csrf_token"]})
    assert confirmed.status_code == 200
    assert confirmed.get_json()["status"] == "confirmed"
    assert confirmed.get_json()["bin"] == "Biotonne"


def test_local_image_match_suggests_category_without_asking_ki(client, monkeypatch, tmp_path):
    from app.ai_services import AIClient, Classification
    from app import local_vision

    monkeypatch.setenv("LOCAL_VISION_MODEL_DIR", str(tmp_path / "model"))
    monkeypatch.setenv("OPENAI_BASE_URL", "https://chat.kiconnect.nrw/api/v1")

    class FakeLocal:
        def classify(self, image_bytes):
            assert image_bytes.startswith(b"\xff\xd8\xff")
            return Classification("recyclable", "cardboard", 0.0, 0.335)

    monkeypatch.setattr(local_vision, "get_local_vision", lambda path: FakeLocal())
    monkeypatch.setattr(AIClient, "call_vision", lambda *args: pytest.fail("Do not call KI:connect"))
    response = client.post("/api/classify", data={
        "region": "Dortmund", "photo": (BytesIO(photo()), "cardboard.png"),
    })
    assert response.status_code == 200
    result = response.get_json()
    assert result["ai_category"] == "recyclable"
    assert result["stream"] == "paper"
    assert result["status"] == "suggested"
    assert result["match_score"] == pytest.approx(0.335)
    assert result["bin"] == "Check the city's Abfall-ABC"
    page = client.get(f"/scan/{result['scan_id']}").data
    assert b"Visual match score" in page and b"0.335 (cosine similarity; not confidence)" in page
    assert b"Not calibrated / no score" not in page


@pytest.mark.parametrize("description,category", [
    ("plastic bottle", "recyclable"),
    ("battery", "unknown"),
    ("random item", "unknown"),
    ("apple juice carton", "unknown"),
])
def test_ambiguous_text_requires_confirmation(client, monkeypatch, description, category):
    from app.ai_services import AIService

    monkeypatch.setattr(AIService, "classify_upload", lambda *args: pytest.fail("Text-only must not send a photo"))
    result = client.post("/api/classify", data={"region": "Berlin", "description": description}).get_json()
    assert result["ai_category"] == category
    assert result["stream"] == "unknown"
    assert result["needs_confirmation"] is True
    assert result["bin"] == "Check the city's Abfall-ABC"
    assert b"Text lookup only" in client.get(f"/scan/{result['scan_id']}").data
    assert b"Confirm my chosen route" in client.get(f"/scan/{result['scan_id']}").data
    assert client.get("/api/stats").get_json()["category_counts"]["unknown"] == 1


@pytest.mark.parametrize("description", [
    "Apple", "BANANA", "apple peel", "banana peel", "strawberry", "orange", "pear", "fruit",
])
def test_named_fruit_text_auto_routes_and_is_editable(client, description):
    result = client.post("/api/classify", data={"region": "Berlin", "description": description}).get_json()
    assert result["status"] == "auto_routed"
    assert result["ai_category"] == result["category"] == "compostable"
    assert result["stream"] == "bio"
    assert result["needs_confirmation"] is False
    assert result["bin"] == "Biotonne"
    assert result["material"] == description
    assert result["match_score"] is None
    page = client.get(f"/scan/{result['scan_id']}").data
    assert b"Auto-routed from text" in page
    assert b"Wrong item or route? Correct it" in page
    assert b"TEXT-BASED ROUTE" in page
    assert b"Item name (optional)" in page
    assert b"Visual match score" not in page
    assert client.get("/api/stats").get_json()["stream_counts"]["bio"] == 1


def test_photo_and_description_agreement_and_mismatch(client, monkeypatch):
    from app.ai_services import AIService

    monkeypatch.setattr(AIService, "classify_upload", lambda self, image, region: {
        "category": "compostable", "material": "banana peel", "confidence": 0,
        "region": region,
    })
    matched = client.post("/api/classify", data={
        "region": "Dortmund", "description": "banana peel", "photo": (BytesIO(photo()), "item.png"),
    }).get_json()
    assert matched["stream"] == "bio"
    assert matched["status"] == "suggested"
    assert matched["bin"] == "Check the city's Abfall-ABC"
    assert b"Photo and description appear consistent" in client.get(f"/scan/{matched['scan_id']}").data
    mismatch = client.post("/api/classify", data={
        "region": "Dortmund", "description": "glass bottle", "photo": (BytesIO(photo()), "item.png"),
    }).get_json()
    assert mismatch["stream"] == "unknown"
    assert mismatch["ai_category"] == "unknown"
    assert mismatch["material"] == "glass bottle"
    assert b"did not agree" in client.get(f"/scan/{mismatch['scan_id']}").data
    assert client.get("/api/stats").get_json()["category_counts"]["unknown"] == 2


def test_photo_cannot_verify_claim_when_vision_disabled(client, monkeypatch):
    from app.ai_services import AIClient

    monkeypatch.setenv("OPENAI_BASE_URL", "https://chat.kiconnect.nrw/api/v1")
    monkeypatch.setattr(AIClient, "call_vision", lambda *args: pytest.fail("No unsafe provider call"))
    result = client.post("/api/classify", data={
        "region": "Berlin", "description": "banana peel", "photo": (BytesIO(photo()), "item.png"),
    }).get_json()
    assert result["status"] == "unresolved"
    assert result["ai_category"] == "unknown"
    assert result["bin"] == "Check the city's Abfall-ABC"


def test_broad_banana_photo_does_not_validate_peel_claim(client, monkeypatch):
    from app.ai_services import AIService

    monkeypatch.setattr(AIService, "classify_upload", lambda self, image, region: {
        "category": "compostable", "material": "banana (whole fruit or peel)",
        "confidence": 0, "region": region,
    })
    result = client.post("/api/classify", data={
        "region": "Berlin", "description": "banana peel", "photo": (BytesIO(photo()), "item.png"),
    }).get_json()
    assert result["ai_category"] == "compostable"
    assert result["stream"] == "bio"
    assert result["category"] == "unknown"
    assert result["bin"] == "Check the city's Abfall-ABC"
    assert b"cannot confirm its exact form" in client.get(f"/scan/{result['scan_id']}").data
    page = client.get(f"/scan/{result['scan_id']}").data
    assert b'value="banana (whole fruit or peel)"' in page
    assert b"Confirm suggested route" in page
    saved = client.post(f"/api/scans/{result['scan_id']}/correct", json={
        "stream": "bio", "material": "", "version": 0,
    }, headers={"X-CSRF-Token": result["csrf_token"]})
    assert saved.status_code == 200
    assert saved.get_json()["status"] == "confirmed"
    assert saved.get_json()["material"] == "banana (whole fruit or peel)"
    assert saved.get_json()["bin"] == "Biotonne"


def test_high_reported_score_is_visible_but_never_auto_assigns_bin(client, monkeypatch):
    from app.ai_services import AIService

    monkeypatch.setattr(AIService, "classify_upload", lambda self, image, region: {
        "category": "recyclable", "material": "plastic bottle", "confidence": 0.99,
        "region": region,
    })
    result = client.post("/api/classify", data={
        "region": "Berlin", "photo": (BytesIO(photo()), "bottle.png"),
    }).get_json()
    assert result["ai_category"] == "recyclable"
    assert result["category"] == "unknown"
    assert result["status"] == "unresolved"
    assert result["bin"] == "Check the city's Abfall-ABC"
    page = client.get(f"/scan/{result['scan_id']}").data
    assert b"99% (not verified accuracy)" in page
    assert b"Could this be a Pfand bottle?" in page
    assert b"Illustration of a Pfand bottle return machine" in page
    assert client.get("/api/stats").get_json()["category_counts"]["unknown"] == 1


def test_confirmed_deposit_shows_pfand_illustration(client):
    created = client.post("/api/classify", data={
        "region": "Berlin", "description": "plastic bottle",
    }).get_json()
    response = client.post(f"/api/scans/{created['scan_id']}/correct", json={
        "stream": "deposit", "material": "Pfand plastic bottle", "version": 0,
    }, headers={"X-CSRF-Token": created["csrf_token"]})
    assert response.status_code == 200
    page = client.get(f"/scan/{created['scan_id']}").data
    assert b"Pfand return point" in page
    assert b"Illustration of a Pfand bottle return machine" in page


def test_web_form_text_only_reaches_result_and_correction(client):
    response = client.post("/scan", data={"region": "Berlin", "description": "banana peel"})
    assert response.status_code == 200
    assert b"Auto-routed from text" in response.data
    assert b"Biotonne" in response.data
    with client.session_transaction() as sess:
        token = sess["scan_csrf"]
    saved = client.post("/scan/1/correct", data={
        "stream": "bio", "material": "banana peel", "version": 0, "csrf_token": token,
    })
    assert saved.status_code == 303
    assert saved.headers["Location"].endswith("/dashboard")
    dashboard = client.get(saved.headers["Location"]).data
    assert b"Confirmation saved." in dashboard
    assert b"banana peel" in dashboard
    assert b"Review / correct" in dashboard
    assert client.get("/api/stats").get_json()["stream_counts"]["bio"] == 1


def test_exact_photo_reuses_only_confirmed_choice_in_same_city_and_browser(client, monkeypatch):
    from app.ai_services import AIService

    calls = []
    def classify(self, image_bytes, region):
        calls.append(region)
        return {"category": "compostable", "material": "banana (whole fruit or peel)",
                "confidence": 0, "match_score": 0.331, "region": region}

    monkeypatch.setattr(AIService, "classify_upload", classify)
    def upload(browser, city="Berlin", image=None, filename="banana.png"):
        return browser.post("/api/classify", data={
            "region": city, "photo": (BytesIO(image if image is not None else photo()), filename),
        }).get_json()

    first = upload(client)
    assert first["status"] == "suggested"
    assert upload(client)["needs_confirmation"] is True  # not confirmed yet
    assert len(calls) == 2
    # Confirm the most recent suggestion; pending uploads do not grant trust.
    latest_id = 2
    saved = client.post(f"/api/scans/{latest_id}/correct", json={
        "stream": "bio", "material": "banana peel", "version": 0,
    }, headers={"X-CSRF-Token": first["csrf_token"]}).get_json()
    assert saved["status"] == "corrected"
    repeat = upload(client, filename="same-photo.jpg")
    assert repeat["previously_confirmed"] is True
    assert repeat["scan_id"] == latest_id
    assert repeat["material"] == "banana peel"
    assert repeat["status"] == "corrected"
    assert repeat["bin"] == "Biotonne"
    assert repeat["match_score"] == pytest.approx(0.331)
    assert len(calls) == 2
    page = client.post("/scan", data={"region": "Berlin", "photo": (BytesIO(photo()), "same.png")}).data
    assert b"Previously confirmed by you" in page
    assert b"Save my correction" in page
    assert b"0.331 (cosine similarity; not confidence)" in page
    assert client.get("/api/stats").get_json()["total_scans"] == 2
    assert upload(client, city="Dortmund")["needs_confirmation"] is True
    assert upload(client, image=other_photo())["needs_confirmation"] is True
    other_browser = client.application.test_client()
    assert upload(other_browser)["needs_confirmation"] is True
    assert len(calls) == 5


def test_photo_hash_is_added_to_existing_sqlite_without_losing_scans(tmp_path, monkeypatch):
    import sqlite3
    from app.db import SCHEMA_PATH

    path = tmp_path / "before-photo-index.db"
    schema = SCHEMA_PATH.read_text(encoding="utf-8").split("-- No photos stored:")[0]
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
        connection.execute("INSERT INTO scans (timestamp, region, category, material, confidence) VALUES (?,?,?,?,?)",
                           ("2026-11-07T10:00:00", "Berlin", "unknown", "old scan", 0))
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.delenv("DB_HOST", raising=False)
    browser = create_app().test_client()
    assert browser.get("/api/stats").get_json()["total_scans"] == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM photo_uploads").fetchone()[0] == 0
        assert connection.execute("SELECT material FROM scans WHERE id=1").fetchone()[0] == "old scan"


def test_confirming_earlier_of_two_pending_photo_scans_still_reuses_it(client, monkeypatch):
    from app.ai_services import AIService

    calls = []
    def classify(self, image_bytes, region):
        calls.append(region)
        return {"category": "compostable", "material": "banana", "confidence": 0,
                "match_score": 0.33, "region": region}

    monkeypatch.setattr(AIService, "classify_upload", classify)
    def submit():
        return client.post("/api/classify", data={
            "region": "Berlin", "photo": (BytesIO(photo()), "banana.png"),
        }).get_json()

    first, second = submit(), submit()
    assert first["scan_id"] != second["scan_id"]
    saved = client.post(f"/api/scans/{first['scan_id']}/correct", json={
        "stream": "bio", "material": "", "version": 0,
    }, headers={"X-CSRF-Token": first["csrf_token"]})
    assert saved.status_code == 200
    reused = submit()
    assert reused["previously_confirmed"] is True
    assert reused["scan_id"] == first["scan_id"]
    assert len(calls) == 2


def test_reuse_respects_user_corrected_route_not_model_category(client, monkeypatch):
    from app.ai_services import AIService

    def classify(self, image_bytes, region):
        return {"category": "compostable", "material": "banana", "confidence": 0,
                "match_score": 0.31, "region": region}

    monkeypatch.setattr(AIService, "classify_upload", classify)
    def upload():
        return client.post("/api/classify", data={
            "region": "Berlin", "photo": (BytesIO(photo()), "banana.png"),
        }).get_json()

    first = upload()
    corrected = client.post(f"/api/scans/{first['scan_id']}/correct", json={
        "stream": "packaging", "material": "plastic wrapper", "version": 0,
    }, headers={"X-CSRF-Token": first["csrf_token"]}).get_json()
    assert corrected["status"] == "corrected"
    repeated = upload()
    assert repeated["previously_confirmed"] is True
    assert repeated["stream"] == "packaging"
    assert repeated["material"] == "plastic wrapper"
    assert repeated["ai_category"] == "compostable"
    assert repeated["match_score"] == pytest.approx(0.31)


def test_apple_text_is_immediately_routed_and_can_be_corrected(client):
    response = client.post("/api/classify", data={"region": "Dortmund", "description": "Apple"})
    result = response.get_json()
    assert result["ai_category"] == "compostable"
    assert result["stream"] == "bio"
    assert result["status"] == "auto_routed"
    assert result["bin"] == "Biotonne"
    page = client.get(f"/scan/{result['scan_id']}").data
    assert b"discarded fruit" in page
    assert b'value="Apple"' in page
    saved = client.post(f"/api/scans/{result['scan_id']}/correct", json={
        "stream": "bio", "material": "", "version": 0,
    }, headers={"X-CSRF-Token": result["csrf_token"]})
    assert saved.status_code == 200
    assert saved.get_json()["material"] == "Apple"
    assert saved.get_json()["status"] == "confirmed"
    assert saved.get_json()["bin"] == "Biotonne"
    assert client.get("/api/stats").get_json()["stream_counts"]["bio"] == 1


@pytest.mark.parametrize("data", [
    {"region": "Berlin", "description": "   "},
    {"region": "Berlin", "description": "x" * 121},
    {"region": "Berlin", "description": "banana\npeel"},
    {"region": "Wrong", "description": "banana peel"},
])
def test_description_validation(client, data):
    assert client.post("/api/classify", data=data).status_code == 400


def test_compose_waits_for_real_mysql_tcp_query():
    from pathlib import Path
    compose = (Path(__file__).resolve().parent.parent / "docker-compose.yml").read_text()
    assert "mysqladmin" not in compose
    assert "--protocol=TCP -h 127.0.0.1" in compose
    assert "SELECT 1" in compose
    assert 'restart: on-failure' in compose
    override = (Path(__file__).resolve().parent.parent / "docker-compose.vision.yml").read_text()
    assert 'source: ${LOCAL_VISION_MODEL_DIR:' in override
    assert 'target: /opt/waste-vision' in override
    assert 'read_only: true' in override


def test_old_unconfirmed_suggestions_are_not_in_dashboard(client):
    from datetime import datetime
    from app.db import Scan, ScanRepository, create_database
    from app.scan_reviews import ReviewRepository

    with client.session_transaction() as sess:
        sess["scan_owner"] = "test-owner"
    with create_database() as database:
        scan_id = ScanRepository(database).save_scan(
            Scan(None, datetime(2026, 11, 7), "Berlin", "compostable", "banana peel", 0.7))
        ReviewRepository(database).create(scan_id, "test-owner", "bio", {
            "category": "compostable", "material": "banana peel", "confidence": 0.7,
        })
        ReviewRepository(database).reconcile_pending()
    stats = client.get("/api/stats").get_json()
    assert stats["category_counts"]["unknown"] == 1
    assert stats["stream_counts"]["bio"] == 0
    assert stats["stream_counts"]["unknown"] == 1


def test_existing_review_rows_gain_optional_score_column(tmp_path, monkeypatch):
    import sqlite3
    from app.db import SCHEMA_PATH

    path = tmp_path / "old-reviews.db"
    schema = SCHEMA_PATH.read_text(encoding="utf-8").replace(
        "    match_score REAL DEFAULT NULL,        -- optional raw image/text similarity, not confidence\n", "")
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
        connection.execute(
            "INSERT INTO scans (timestamp, region, category, material, confidence) VALUES (?,?,?,?,?)",
            ("2026-11-07T10:00:00", "Berlin", "unknown", "banana peel", 0.0),
        )
        connection.execute(
            "INSERT INTO scan_reviews (scan_id, owner_hash, stream, status, ai_category, ai_material, ai_confidence) "
            "VALUES (1,'old-owner','bio','suggested','compostable','banana peel',0)")
    monkeypatch.setenv("DB_PATH", str(path))
    monkeypatch.delenv("DB_HOST", raising=False)
    app = create_app()
    assert app.test_client().get("/api/stats").status_code == 200
    with sqlite3.connect(path) as connection:
        assert "match_score" in {row[1] for row in connection.execute("PRAGMA table_info(scan_reviews)")}
        assert connection.execute("SELECT ai_material, match_score FROM scan_reviews WHERE scan_id=1").fetchone() == ("banana peel", None)


def test_missing_local_model_does_not_fall_back_to_unverified_ki(client, monkeypatch, tmp_path):
    from app.ai_services import AIClient

    monkeypatch.setenv("LOCAL_VISION_MODEL_DIR", str(tmp_path / "not-installed"))
    monkeypatch.setattr(AIClient, "call_vision", lambda *args: pytest.fail("Do not call KI:connect"))
    response = client.post("/api/classify", data={
        "region": "Dortmund", "photo": (BytesIO(photo()), "item.png"),
    })
    assert response.status_code == 200
    assert response.get_json()["category"] == "unknown"
    assert response.get_json()["material"] == "local vision unavailable"


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
