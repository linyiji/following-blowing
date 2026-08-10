from __future__ import annotations

import base64
import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from app.config import PROJECT_ROOT

from .models import AssetMetadata, StoredAsset
from .storage import LocalAssetStorage
from .validators import ImageValidationPolicy, sanitize_filename, validate_image


class AssetService:
    def __init__(
        self,
        storage: LocalAssetStorage | None = None,
        *,
        policy: ImageValidationPolicy | None = None,
    ) -> None:
        self.storage = storage or LocalAssetStorage(PROJECT_ROOT / "data" / "assets")
        self.policy = policy or ImageValidationPolicy()

    @staticmethod
    def _read_source(source: bytes | bytearray | Path | str | BinaryIO | Any) -> tuple[bytes, str | None, str | None]:
        if isinstance(source, (bytes, bytearray)):
            return bytes(source), None, None
        if isinstance(source, (Path, str)):
            path = Path(source)
            return path.read_bytes(), path.name, None
        name = getattr(source, "name", None)
        mime_type = getattr(source, "type", None)
        if hasattr(source, "getvalue"):
            return bytes(source.getvalue()), name, mime_type
        if hasattr(source, "read"):
            value = source.read()
            if isinstance(value, str):
                value = value.encode("utf-8")
            return bytes(value), name, mime_type
        raise TypeError("Asset source must be bytes, a path, or a binary file object")

    def ingest(
        self,
        source: bytes | bytearray | Path | str | BinaryIO | Any,
        *,
        filename: str | None = None,
        declared_mime: str | None = None,
        source_type: str = "upload",
    ) -> StoredAsset:
        data, inferred_name, inferred_mime = self._read_source(source)
        original_name = filename or inferred_name or "asset"
        validated = validate_image(
            data,
            original_name,
            declared_mime=declared_mime or inferred_mime,
            policy=self.policy,
        )
        digest = hashlib.sha256(data).hexdigest()
        asset_id = f"asset_{digest[:24]}"
        safe_stem = Path(sanitize_filename(original_name)).stem
        safe_filename = f"{safe_stem}-{digest[:12]}{validated.extension}"
        metadata = AssetMetadata(
            asset_id=asset_id,
            original_filename=Path(str(original_name).replace("\\", "/")).name,
            safe_filename=safe_filename,
            mime_type=validated.mime_type,
            extension=validated.extension,
            size_bytes=len(data),
            width=validated.width,
            height=validated.height,
            sha256=digest,
            created_at=datetime.now(timezone.utc).isoformat(),
            source=source_type,
        )
        return self.storage.save(data, metadata)

    def ingest_demo(self, path: Path | str) -> StoredAsset:
        demo_path = Path(path).resolve()
        demo_root = (PROJECT_ROOT / "assets" / "demo").resolve()
        if demo_root not in demo_path.parents:
            raise ValueError("Demo assets must come from assets/demo")
        return self.ingest(demo_path, source_type="demo")

    def get(self, asset_id: str) -> StoredAsset:
        return self.storage.get(asset_id)

    def preview_data_uri(self, asset_id: str, *, max_bytes: int = 2 * 1024 * 1024) -> str | None:
        asset = self.get(asset_id)
        data = asset.path.read_bytes()
        if len(data) > max_bytes:
            preview = self._bounded_preview(data, max_bytes=max_bytes)
            if preview is None:
                return None
            data, mime_type = preview
        else:
            mime_type = asset.mime_type
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _bounded_preview(data: bytes, *, max_bytes: int) -> tuple[bytes, str] | None:
        """Create a browser preview without mirroring a large upload in state."""

        if max_bytes <= 0:
            return None
        try:
            from PIL import Image, ImageOps  # type: ignore

            with Image.open(io.BytesIO(data)) as source:
                normalized = ImageOps.exif_transpose(source)
                if normalized.mode in {"RGBA", "LA"} or (
                    normalized.mode == "P" and "transparency" in normalized.info
                ):
                    rgba = normalized.convert("RGBA")
                    rgb = Image.new("RGB", rgba.size, "white")
                    rgb.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    rgb = normalized.convert("RGB")

                for dimension in (1280, 960, 720, 512, 384, 256, 192, 128):
                    candidate = rgb.copy()
                    candidate.thumbnail((dimension, dimension), Image.Resampling.LANCZOS)
                    for quality in (82, 70, 55, 40):
                        output = io.BytesIO()
                        candidate.save(
                            output,
                            format="JPEG",
                            quality=quality,
                            optimize=True,
                            progressive=True,
                        )
                        encoded = output.getvalue()
                        if len(encoded) <= max_bytes:
                            return encoded, "image/jpeg"
        except (ImportError, OSError, ValueError):
            return None
        return None


__all__ = ["AssetService"]
