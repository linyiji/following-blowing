"""Validated, serializable metadata for a locally materialized image.

The absolute filesystem path is deliberately kept in a Pydantic private
attribute.  Checkpoints and browser-facing payloads therefore only receive a
path relative to the caller-selected artifact root.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from app.services.errors import ImageGenerationError


class ImageArtifact(BaseModel):
    """Normalized metadata for an image that has passed local validation."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=1)
    local_path: str
    mime_type: str
    format: str
    byte_size: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    request_id: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)

    _absolute_path: Path | None = PrivateAttr(default=None)

    @field_validator("local_path")
    @classmethod
    def _relative_local_path(cls, value: str) -> str:
        path = Path(value)
        if (
            not value.strip()
            or path.is_absolute()
            or ".." in path.parts
            or re.match(r"^[A-Za-z]:[\\/]", value)
        ):
            raise ValueError("local_path must be a safe relative path")
        return path.as_posix()

    def bind_absolute_path(self, path: Path | str) -> "ImageArtifact":
        self._absolute_path = Path(path).resolve()
        return self

    @property
    def absolute_path(self) -> Path:
        if self._absolute_path is None:
            raise ImageGenerationError("Image artifact is not bound to a local file")
        return self._absolute_path

    @property
    def local_file(self) -> Path:
        """Backend-only absolute path; omitted from every serialized payload."""

        return self.absolute_path

    @property
    def path(self) -> Path:
        """Compatibility alias used by the existing generation Agent."""

        return self.absolute_path

    def __fspath__(self) -> str:
        return str(self.absolute_path)


def normalize_image_artifact(
    path: Path | str,
    *,
    relative_to: Path | str,
    provider: str,
    model: str,
    request_id: str | None = None,
    latency_ms: int | None = None,
) -> ImageArtifact:
    """Validate a local image and return safe, project-relative metadata."""

    absolute = Path(path).resolve()
    if not absolute.is_file() or absolute.stat().st_size <= 0:
        raise ImageGenerationError("Image provider returned an empty result")
    byte_size = absolute.stat().st_size

    try:
        with Image.open(absolute) as image:
            image.verify()
        with Image.open(absolute) as image:
            image.load()
            width, height = image.size
            detected_format = str(image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageGenerationError("Image provider returned an unreadable image") from exc

    if not detected_format or width <= 0 or height <= 0:
        raise ImageGenerationError("Image provider returned invalid image dimensions")
    mime_type = Image.MIME.get(detected_format)
    if not mime_type:
        mime_type = mimetypes.guess_type(absolute.name)[0]
    if not mime_type or not mime_type.startswith("image/"):
        raise ImageGenerationError("Image provider returned an unsupported image format")

    digest = hashlib.sha256(absolute.read_bytes()).hexdigest()
    root = Path(relative_to).resolve()
    try:
        relative = absolute.relative_to(root)
    except ValueError:
        # Never serialize an absolute path or a traversal outside the selected
        # artifact root.  The private path remains available to backend code.
        relative = Path(absolute.name)

    artifact = ImageArtifact(
        artifact_id=f"image-{digest[:20]}",
        local_path=relative.as_posix(),
        mime_type=mime_type,
        format=detected_format,
        byte_size=byte_size,
        width=width,
        height=height,
        sha256=digest,
        provider=provider,
        model=model,
        request_id=request_id,
        latency_ms=latency_ms,
    )
    return artifact.bind_absolute_path(absolute)


__all__ = ["ImageArtifact", "normalize_image_artifact"]
