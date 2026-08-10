"""Compatibility facade for the canonical :mod:`app.assets` package."""

from app.assets import (
    AssetMetadata,
    AssetService,
    AssetValidationError,
    ImageValidationPolicy,
    LocalAssetStorage,
    StoredAsset,
)

__all__ = [
    "AssetMetadata",
    "AssetService",
    "AssetValidationError",
    "ImageValidationPolicy",
    "LocalAssetStorage",
    "StoredAsset",
]
