import io
import uuid

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB, checked before Pillow touches the file
MAX_PIXELS = 50_000_000  # ~50MP; guards against decompression bombs
MAX_DIMENSION = 1600  # longest side after resize
WEBP_QUALITY = 80

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


class ImageValidationError(Exception):
    """Raised with a user-facing message when an uploaded image is rejected."""


def process_image(uploaded_file) -> ContentFile:
    """
    Validates an uploaded image and re-encodes it as a resized WebP.

    Order matters: the size check runs before Pillow parses anything,
    the pixel check runs before the full decode, and only then is the
    image loaded, rotated per EXIF, shrunk and re-saved. Re-encoding
    also drops EXIF metadata (often GPS location) and anything else
    appended to the original file, so what lands in media/ is always a
    clean image Pillow wrote itself — never the raw upload.

    Returns a ContentFile with a random .webp name, ready to assign to
    an ImageField. Raises ImageValidationError with a message safe to
    show the client.
    """
    if uploaded_file.size == 0:
        raise ImageValidationError("File is empty.")
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise ImageValidationError(
            f"File is too large ({uploaded_file.size / (1024 * 1024):.1f}MB). "
            f"Maximum allowed size is {MAX_UPLOAD_BYTES // (1024 * 1024)}MB."
        )

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as probe:
            image_format = probe.format
            width, height = probe.size
            probe.verify()
    except UnidentifiedImageError:
        raise ImageValidationError(
            "File is not a valid image. Allowed formats: JPEG, PNG, WebP."
        )
    except Image.DecompressionBombError:
        raise ImageValidationError("Image dimensions are too large.")
    except Exception:
        raise ImageValidationError("Image file is corrupted or could not be read.")

    if image_format not in ALLOWED_FORMATS:
        raise ImageValidationError(
            f"Unsupported image format ({image_format}). "
            "Allowed formats: JPEG, PNG, WebP."
        )
    if width * height > MAX_PIXELS:
        raise ImageValidationError(
            f"Image dimensions are too large ({width}x{height}). "
            "Please upload a smaller image."
        )

    # verify() leaves the image unusable, so reopen for the real decode.
    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert(
                    "RGBA" if "transparency" in img.info or "A" in img.mode else "RGB"
                )
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=6)
    except Image.DecompressionBombError:
        raise ImageValidationError("Image dimensions are too large.")
    except Exception:
        raise ImageValidationError("Image file is corrupted or could not be processed.")

    return ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.webp")
