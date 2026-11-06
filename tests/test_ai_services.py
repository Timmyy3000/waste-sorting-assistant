"""Unit tests for subsystem A (AI Services).

OpenAI is never called: a mock AIClient returns fixed answers, so the tests are fast,
free and always give the same result. These are black-box tests: they only check what
goes in (an image) and what comes out (a Classification or an error).
"""

from unittest.mock import Mock

import pytest

from app.ai_services import (
    AIClient,
    AIService,
    AIUnavailableError,
    ImageTooLargeError,
    InvalidImageError,
    MAX_IMAGE_BYTES,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
JPEG = b"\xff\xd8\xff" + b"0" * 100


@pytest.fixture
def client():
    """A fake AIClient: same methods as the real one, but no network calls."""
    fake = Mock(spec=AIClient)
    fake.call_vision.return_value = '{"category": "recyclable", "material": "plastic bottle", "confidence": 0.92}'
    fake.call_text.return_value = "Rinse it and put it in the yellow bin."
    return fake


@pytest.fixture
def service(client):
    return AIService(client)


def test_valid_image_is_classified(service, client):
    result = service.classify_image(PNG)

    assert result.category == "recyclable"
    assert result.material == "plastic bottle"
    assert result.confidence == 0.92
    assert result.needs_confirmation is False
    client.call_vision.assert_called_once()


def test_wrong_file_type_is_rejected(service, client):
    with pytest.raises(InvalidImageError):
        service.classify_image(b"GIF89a this is not a jpeg or png")

    client.call_vision.assert_not_called()  # rejected before any API call


def test_image_over_5_mb_is_rejected(service, client):
    too_big = JPEG + b"0" * MAX_IMAGE_BYTES

    with pytest.raises(ImageTooLargeError):
        service.classify_image(too_big)

    client.call_vision.assert_not_called()


def test_api_failure_retries_once_then_asks_for_manual_selection(service, client):
    client.call_vision.side_effect = ConnectionError("network down")

    with pytest.raises(AIUnavailableError, match="manually"):
        service.classify_image(PNG)

    assert client.call_vision.call_count == 2  # first try + one retry
