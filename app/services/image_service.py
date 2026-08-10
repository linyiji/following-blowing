from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Sequence

from app.providers.image_artifact import ImageArtifact, normalize_image_artifact
from app.providers.image_base import ImageInput, ImageProvider
from app.services.errors import ImageGenerationError

from .run_service import LocalRunRepository


class ImageService:
    def __init__(
        self,
        provider: ImageProvider,
        repository: LocalRunRepository,
        *,
        max_generations_per_run: int = 3,
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.max_generations_per_run = max_generations_per_run

    def _destination(self, run_id: str, number: int) -> Path:
        return self.repository.ensure_artifact_layout(run_id) / "candidates" / f"candidate_{number:02d}.png"

    def generate_candidate(
        self,
        run_id: str,
        *,
        prompt: str,
        reference_images: Sequence[ImageInput] | None = None,
        **kwargs: Any,
    ) -> ImageArtifact:
        run = self.repository.get_run(run_id)
        count = int(run.get("image_generation_calls", 0))
        if count >= self.max_generations_per_run:
            raise ImageGenerationError("Image generation limit reached for this workflow run")
        destination = self._destination(run_id, count + 1)
        if reference_images:
            result = self.provider.edit_with_reference(
                reference_images=reference_images,
                prompt=prompt,
                output_path=destination,
                **kwargs,
            )
        else:
            result = self.provider.generate(prompt=prompt, output_path=destination, **kwargs)
        provider_name = type(self.provider).__name__
        provider_model = str(getattr(getattr(self.provider, "settings", None), "model", "unknown"))
        request_id: str | None = None
        latency_ms: int | None = None
        if isinstance(result, ImageArtifact):
            source = result.absolute_path
            provider_name = result.provider
            provider_model = result.model
            request_id = result.request_id
            latency_ms = result.latency_ms
            if source != destination:
                if not source.is_file():
                    raise ImageGenerationError("Image provider did not return a usable file")
                shutil.copyfile(source, destination)
        elif isinstance(result, bytes):
            destination.write_bytes(result)
        elif Path(result) != destination:
            source = Path(result)
            if not source.is_file():
                raise ImageGenerationError("Image provider did not return a usable file")
            shutil.copyfile(source, destination)
        artifact = normalize_image_artifact(
            destination,
            relative_to=self.repository.run_dir(run_id),
            provider=provider_name,
            model=provider_model,
            request_id=request_id,
            latency_ms=latency_ms,
        )
        self.repository.write_artifact(
            run_id,
            f"candidates/{destination.stem}.json",
            artifact,
        )
        self.repository.update_run(run_id, image_generation_calls=count + 1)
        return artifact

    def mark_final_candidate(
        self, run_id: str, candidate: ImageArtifact | Path | str
    ) -> Path:
        source = (
            candidate.absolute_path
            if isinstance(candidate, ImageArtifact)
            else Path(candidate)
        )
        if not source.is_file():
            raise FileNotFoundError(source)
        suffix = source.suffix.lower() or ".png"
        destination = self.repository.ensure_artifact_layout(run_id) / "output" / f"result{suffix}"
        shutil.copyfile(source, destination)
        self.repository.update_run(run_id, final_candidate_id=source.stem)
        return destination


__all__ = ["ImageService"]
