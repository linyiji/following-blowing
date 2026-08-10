from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from app.config import ProviderSettings
from app.providers.client import ProviderClient
from app.providers.image_artifact import ImageArtifact, normalize_image_artifact
from app.providers.openai_image import OpenAIImageProvider
from app.services.errors import ImageGenerationError
from app.services.image_service import ImageService
from app.services.run_service import LocalRunRepository


def _png_bytes(*, width: int = 7, height: int = 5) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), (220, 20, 40)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_normalized_artifact_is_valid_and_never_serializes_absolute_path(
    tmp_path: Path,
) -> None:
    output = tmp_path / "root" / "candidates" / "candidate.png"
    output.parent.mkdir(parents=True)
    payload = _png_bytes()
    output.write_bytes(payload)

    artifact = normalize_image_artifact(
        output,
        relative_to=tmp_path / "root",
        provider="openai",
        model="gpt-image-2",
        request_id="request-test",
        latency_ms=17,
    )

    assert artifact.local_path == "candidates/candidate.png"
    assert artifact.absolute_path == output.resolve()
    assert artifact.mime_type == "image/png"
    assert artifact.format == "PNG"
    assert artifact.byte_size == len(payload)
    assert (artifact.width, artifact.height) == (7, 5)
    assert artifact.sha256 == hashlib.sha256(payload).hexdigest()
    assert artifact.provider == "openai"
    assert artifact.model == "gpt-image-2"
    dumped = artifact.model_dump(mode="json")
    assert "absolute_path" not in dumped
    assert str(tmp_path.resolve()) not in repr(dumped)

    with pytest.raises(ValidationError, match="safe relative path"):
        ImageArtifact(**{**dumped, "local_path": str(output.resolve())})


def test_normalization_rejects_unreadable_provider_output(tmp_path: Path) -> None:
    output = tmp_path / "broken.png"
    output.write_bytes(b"not-an-image")

    with pytest.raises(ImageGenerationError, match="unreadable image"):
        normalize_image_artifact(
            output,
            relative_to=tmp_path,
            provider="fake",
            model="fake-image",
        )


class _FakeImages:
    def __init__(self, image_bytes: bytes) -> None:
        self.image_bytes = image_bytes
        self.generate_calls: list[dict] = []
        self.edit_calls: list[dict] = []

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(self.image_bytes).decode())],
            _request_id="sdk-generation-request",
        )

    def edit(self, **kwargs):
        self.edit_calls.append(
            {
                **kwargs,
                "image_is_list": isinstance(kwargs.get("image"), list),
                "image_name": getattr(kwargs.get("image"), "name", None),
            }
        )
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=base64.b64encode(self.image_bytes).decode())],
            _request_id="sdk-edit-request",
        )


def _openai_provider(fake_images: _FakeImages) -> OpenAIImageProvider:
    provider = OpenAIImageProvider(
        ProviderSettings(
            provider="openai",
            model="gpt-image-2",
            api_key="test-key",
        ),
        client=ProviderClient(max_retries=0),
    )
    provider._sdk_client = SimpleNamespace(images=fake_images)
    return provider


def test_openai_edit_uses_one_file_and_returns_request_metadata(tmp_path: Path) -> None:
    source = tmp_path / "reference.png"
    source.write_bytes(_png_bytes(width=4, height=6))
    output = tmp_path / "edited.png"
    images = _FakeImages(_png_bytes(width=12, height=9))
    provider = _openai_provider(images)

    artifact = provider.edit_with_reference(
        reference_images=[source],
        prompt="preserve identity and add a small red hat",
        output_path=output,
        quality="low",
    )

    assert isinstance(artifact, ImageArtifact)
    assert images.edit_calls[0]["image_is_list"] is False
    assert images.edit_calls[0]["image_name"] == str(source)
    assert images.edit_calls[0]["model"] == "gpt-image-2"
    assert artifact.request_id == "sdk-edit-request"
    assert artifact.latency_ms is not None
    assert artifact.absolute_path == output.resolve()


def test_openai_multi_reference_edit_is_disabled_without_verified_capability(
    tmp_path: Path,
) -> None:
    source_1 = tmp_path / "one.png"
    source_2 = tmp_path / "two.png"
    source_1.write_bytes(_png_bytes())
    source_2.write_bytes(_png_bytes())
    images = _FakeImages(_png_bytes())
    provider = _openai_provider(images)

    assert provider.multi_reference_image_edit is False
    with pytest.raises(ImageGenerationError, match="not verified"):
        provider.edit_with_reference(
            reference_images=[source_1, source_2],
            prompt="unsupported",
            output_path=tmp_path / "unused.png",
        )
    assert images.edit_calls == []


def test_image_service_returns_run_relative_artifact_and_counts_success(
    tmp_path: Path,
) -> None:
    images = _FakeImages(_png_bytes(width=10, height=8))
    provider = _openai_provider(images)
    repository = LocalRunRepository(tmp_path / "runs")
    run = repository.create_run()
    service = ImageService(provider, repository)

    artifact = service.generate_candidate(run["run_id"], prompt="minimal icon")

    assert artifact.local_path == "candidates/candidate_01.png"
    assert artifact.absolute_path.is_file()
    assert artifact.provider == "openai"
    assert artifact.model == "gpt-image-2"
    assert repository.get_run(run["run_id"])["image_generation_calls"] == 1
    sidecar = repository.run_dir(run["run_id"]) / "candidates/candidate_01.json"
    payload = sidecar.read_text(encoding="utf-8")
    assert sidecar.is_file()
    assert artifact.sha256 in payload
    assert str(tmp_path.resolve()) not in payload
