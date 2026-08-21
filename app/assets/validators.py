from __future__ import annotations

import io
import re
import struct
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final


class AssetValidationError(ValueError):
    """Raised when an uploaded asset is unsafe or is not a supported image."""


MIME_EXTENSIONS: Final[dict[str, tuple[str, ...]]] = {
    "image/png": (".png",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/webp": (".webp",),
}


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    mime_type: str
    extension: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ImageValidationPolicy:
    max_bytes: int = 50 * 1024 * 1024
    max_width: int = 12_000
    max_height: int = 12_000
    max_pixels: int = 40_000_000


def sanitize_filename(filename: str, *, fallback: str = "asset") -> str:
    """Return a display-only safe basename; never use user paths directly."""

    basename = Path(str(filename).replace("\\", "/")).name
    normalized = unicodedata.normalize("NFKC", basename)
    stem = Path(normalized).stem
    suffix = Path(normalized).suffix.lower()
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-_")[:80]
    safe_stem = safe_stem or fallback
    safe_suffix = suffix if suffix in {ext for exts in MIME_EXTENSIONS.values() for ext in exts} else ""
    return f"{safe_stem}{safe_suffix}"


def _sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise AssetValidationError("Invalid PNG header")
    return struct.unpack(">II", data[16:24])


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    stream = io.BytesIO(data)
    if stream.read(2) != b"\xff\xd8":
        raise AssetValidationError("Invalid JPEG header")
    while True:
        marker_start = stream.read(1)
        if not marker_start:
            break
        if marker_start != b"\xff":
            continue
        marker = stream.read(1)
        while marker == b"\xff":
            marker = stream.read(1)
        if not marker or marker in {b"\xd8", b"\xd9"}:
            continue
        length_bytes = stream.read(2)
        if len(length_bytes) != 2:
            break
        segment_length = struct.unpack(">H", length_bytes)[0]
        if segment_length < 2:
            break
        if marker[0] in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            payload = stream.read(segment_length - 2)
            if len(payload) < 5:
                break
            height, width = struct.unpack(">HH", payload[1:5])
            return width, height
        stream.seek(segment_length - 2, io.SEEK_CUR)
    raise AssetValidationError("JPEG dimensions could not be read")


def _pillow_dimensions(data: bytes, expected_mime: str) -> tuple[int, int] | None:
    try:
        from PIL import Image, UnidentifiedImageError  # type: ignore
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            mime = Image.MIME.get(image.format or "")
            if mime != expected_mime:
                raise AssetValidationError("Image content does not match its detected format")
            return int(image.width), int(image.height)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise AssetValidationError("Image file is corrupt or unsupported") from exc


def validate_image(
    data: bytes,
    filename: str,
    *,
    declared_mime: str | None = None,
    policy: ImageValidationPolicy | None = None,
) -> ValidatedImage:
    policy = policy or ImageValidationPolicy()
    if not data:
        raise AssetValidationError("Image file is empty")
    if len(data) > policy.max_bytes:
        raise AssetValidationError(f"Image exceeds the {policy.max_bytes} byte limit")

    detected_mime = _sniff_mime(data)
    if detected_mime not in MIME_EXTENSIONS:
        raise AssetValidationError("Only PNG, JPEG, and WebP images are supported")
    if declared_mime and declared_mime.lower() not in {detected_mime, "application/octet-stream"}:
        raise AssetValidationError("Declared MIME type does not match image content")

    suffix = Path(filename).suffix.lower()
    if suffix and suffix not in MIME_EXTENSIONS[detected_mime]:
        raise AssetValidationError("Filename extension does not match image content")

    dimensions = _pillow_dimensions(data, detected_mime)
    if dimensions is None:
        if detected_mime == "image/png":
            dimensions = _png_dimensions(data)
        elif detected_mime == "image/jpeg":
            dimensions = _jpeg_dimensions(data)
        else:
            raise AssetValidationError("WebP validation requires Pillow")
    width, height = dimensions
    if width <= 0 or height <= 0:
        raise AssetValidationError("Image dimensions must be positive")
    if width > policy.max_width or height > policy.max_height or width * height > policy.max_pixels:
        raise AssetValidationError("Image dimensions exceed the configured safety limit")

    canonical_extension = ".jpg" if detected_mime == "image/jpeg" else MIME_EXTENSIONS[detected_mime][0]
    return ValidatedImage(detected_mime, canonical_extension, width, height)


__all__ = [
    "AssetValidationError",
    "ImageValidationPolicy",
    "MIME_EXTENSIONS",
    "ValidatedImage",
    "sanitize_filename",
    "validate_image",
]
