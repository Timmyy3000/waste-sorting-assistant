"""The web upload accepts real images, not merely plausible extensions."""

from io import BytesIO

import pytest
from PIL import Image, features

from app.image_uploads import MAX_PIXELS, normalise
from app.routes.errors import UploadError


def encoded(format, size=(80, 60)):
    data = BytesIO()
    Image.new("RGBA" if format == "PNG" else "RGB", size, "#67a874").save(data, format=format)
    return data.getvalue()


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF"])
def test_common_formats_are_decoded_and_sent_as_jpeg(format):
    data = normalise(encoded(format))
    with Image.open(BytesIO(data)) as image:
        assert image.format == "JPEG"
        assert image.size == (80, 60)


@pytest.mark.skipif(not features.check("avif"), reason="Pillow build has no AVIF decoder")
def test_avif_is_accepted():
    assert normalise(encoded("AVIF")).startswith(b"\xff\xd8\xff")


def test_heic_family_is_accepted_with_decoder():
    pytest.importorskip("pillow_heif")
    assert normalise(encoded("HEIF")).startswith(b"\xff\xd8\xff")


def test_corrupt_and_animated_images_are_rejected():
    with pytest.raises(UploadError, match="readable"):
        normalise(b"\x89PNG\r\n\x1a\nnot really a photo")
    output = BytesIO()
    frames = [Image.new("RGB", (32, 32), colour) for colour in ("red", "blue")]
    frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:])
    with pytest.raises(UploadError, match="Animated"):
        normalise(output.getvalue())


def test_too_many_pixels_is_rejected_before_decoding():
    width = int(MAX_PIXELS ** 0.5) + 1
    data = encoded("PNG", (width, width))
    with pytest.raises(UploadError, match="megapixels"):
        normalise(data)


def test_webp_upload_flows_through_api(tmp_path, monkeypatch):
    from app import create_app
    from app.ai_services import AIService

    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "webp.db"))
    monkeypatch.setattr(AIService, "classify_upload", lambda self, data, region: {
        "category": "unknown", "material": "unverified item", "confidence": 0,
        "region": region, "needs_confirmation": True, "tip": "Check the guide.",
    } if data.startswith(b"\xff\xd8\xff") else pytest.fail("Must normalise before sending"))
    client = create_app().test_client()
    response = client.post("/api/classify", data={
        "region": "Berlin", "photo": (BytesIO(encoded("WEBP")), "photo.webp"),
    })
    assert response.status_code == 200
    assert response.get_json()["stream"] == "unknown"
