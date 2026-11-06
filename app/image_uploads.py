"""Decode and normalise user images before passing them to any vision model."""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.routes.errors import UploadError


MAX_PIXELS = 20_000_000
MAX_SIDE = 1600
SUPPORTED = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "TIFF", "AVIF", "HEIF"}

try:  # Optional decoder for HEIC/HEIF phone photos.
    from pillow_heif import register_heif_opener
except ImportError:
    pass
else:
    register_heif_opener()


def normalise(image_bytes: bytes) -> bytes:
    """Reject corrupt/oversized/animated uploads and produce an oriented JPEG.

    Server-side MIME is determined by actual decoding, never the browser header.
    The converted bytes are only kept in memory for the duration of this request.
    """
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            if source.format not in SUPPORTED:
                raise UploadError("Unsupported image format. Choose a photo, not an SVG or document.")
            width, height = source.size
            if not width or not height or width * height > MAX_PIXELS:
                raise UploadError("This image has too many pixels. Choose one under 20 megapixels.")
            if getattr(source, "n_frames", 1) != 1:
                raise UploadError("Animated images are not supported. Choose a still photo.")
            source.load()
            image = ImageOps.exif_transpose(source)
            image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            if image.mode != "RGB":
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            output = BytesIO()
            image.save(output, "JPEG", quality=85, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise UploadError("This file is not a readable supported image. Try a different photo.") from None
