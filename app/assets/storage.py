from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from .models import AssetMetadata, StoredAsset


_ASSET_ID = re.compile(r"^asset_[0-9a-f]{24}$")


class LocalAssetStorage:
    """Content-addressed local storage with path traversal protection."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _validate_id(self, asset_id: str) -> None:
        if not _ASSET_ID.fullmatch(asset_id):
            raise ValueError("Invalid asset_id")

    def _metadata_path(self, asset_id: str) -> Path:
        self._validate_id(asset_id)
        return self.root / f"{asset_id}.json"

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)

    def save(self, data: bytes, metadata: AssetMetadata) -> StoredAsset:
        self._validate_id(metadata.asset_id)
        content_path = self.root / f"{metadata.asset_id}{metadata.extension}"
        metadata_path = self._metadata_path(metadata.asset_id)
        if not content_path.exists():
            self._atomic_write(content_path, data)
        metadata_bytes = json.dumps(
            metadata.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        self._atomic_write(metadata_path, metadata_bytes)
        return StoredAsset(metadata=metadata, path=content_path)

    def get(self, asset_id: str) -> StoredAsset:
        metadata_path = self._metadata_path(asset_id)
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Asset not found: {asset_id}")
        metadata = AssetMetadata.from_dict(json.loads(metadata_path.read_text(encoding="utf-8")))
        content_path = self.root / f"{asset_id}{metadata.extension}"
        if not content_path.is_file():
            raise FileNotFoundError(f"Asset content is missing: {asset_id}")
        return StoredAsset(metadata=metadata, path=content_path)

    def exists(self, asset_id: str) -> bool:
        try:
            self.get(asset_id)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            return False
        return True

    def delete(self, asset_id: str) -> None:
        stored = self.get(asset_id)
        stored.path.unlink(missing_ok=True)
        self._metadata_path(asset_id).unlink(missing_ok=True)
