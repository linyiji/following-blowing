from __future__ import annotations

import base64
import io

import pytest

from app.assets import AssetService, AssetValidationError, LocalAssetStorage


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_asset_service_validates_hashes_and_uses_safe_storage(tmp_path):
    service = AssetService(LocalAssetStorage(tmp_path / "assets"))
    stored = service.ingest(PNG, filename="../../My IP.png", declared_mime="image/png")

    assert stored.asset_id.startswith("asset_")
    assert stored.path.parent == (tmp_path / "assets").resolve()
    assert ".." not in stored.metadata.safe_filename
    assert stored.metadata.width == 1
    assert service.get(stored.asset_id).metadata.sha256 == stored.metadata.sha256
    assert service.preview_data_uri(stored.asset_id).startswith("data:image/png;base64,")


def test_asset_service_rejects_non_image_and_mime_mismatch(tmp_path):
    service = AssetService(LocalAssetStorage(tmp_path / "assets"))
    with pytest.raises(AssetValidationError):
        service.ingest(b"<script>alert(1)</script>", filename="image.png")
    with pytest.raises(AssetValidationError):
        service.ingest(PNG, filename="image.png", declared_mime="image/jpeg")


def test_asset_id_cannot_traverse_storage(tmp_path):
    storage = LocalAssetStorage(tmp_path / "assets")
    with pytest.raises(ValueError):
        storage.get("../../etc/passwd")


def test_large_asset_preview_is_reencoded_within_browser_budget(tmp_path):
    image_module = pytest.importorskip("PIL.Image")
    image = image_module.effect_noise((900, 900), 100).convert("RGB")
    source = io.BytesIO()
    image.save(source, format="PNG")

    service = AssetService(LocalAssetStorage(tmp_path / "assets"))
    stored = service.ingest(source.getvalue(), filename="large.png")
    preview = service.preview_data_uri(stored.asset_id, max_bytes=30_000)

    assert preview is not None
    header, encoded = preview.split(",", 1)
    assert header == "data:image/jpeg;base64"
    assert len(base64.b64decode(encoded)) <= 30_000
