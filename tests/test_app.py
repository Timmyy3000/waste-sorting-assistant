from app import create_app
from app.config import AppConfig


def test_home_page_loads():
    client = create_app().test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert b"Waste Sorting Assistant" in response.data


def test_placeholder_pages_load():
    client = create_app().test_client()
    assert client.get("/scan").status_code == 200
    assert client.get("/dashboard").status_code == 200


def test_config_properties():
    config = AppConfig()
    config.upload_limit = 1024
    config.allowed_types = {"PNG"}
    assert config.upload_limit == 1024
    assert config.allowed_types == {"png"}
    assert create_app().config["MAX_CONTENT_LENGTH"] == 5 * 1024 * 1024
