from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AssetMetadata:
    asset_id: str
    original_filename: str
    safe_filename: str
    mime_type: str
    extension: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    created_at: str
    source: str = "upload"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AssetMetadata":
        return cls(
            asset_id=str(value["asset_id"]),
            original_filename=str(value["original_filename"]),
            safe_filename=str(value["safe_filename"]),
            mime_type=str(value["mime_type"]),
            extension=str(value["extension"]),
            size_bytes=int(value["size_bytes"]),
            width=int(value["width"]),
            height=int(value["height"]),
            sha256=str(value["sha256"]),
            created_at=str(value["created_at"]),
            source=str(value.get("source", "upload")),
        )


@dataclass(frozen=True, slots=True)
class StoredAsset:
    metadata: AssetMetadata
    path: Path

    @property
    def asset_id(self) -> str:
        return self.metadata.asset_id

    @property
    def mime_type(self) -> str:
        return self.metadata.mime_type

    def to_public_dict(self) -> dict[str, Any]:
        """Browser-safe metadata; the server-local storage path is omitted."""

        return self.metadata.to_dict()
