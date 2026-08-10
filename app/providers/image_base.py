from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Sequence

from .image_artifact import ImageArtifact


ImageInput = bytes | Path | str
ImageOutput = ImageArtifact | bytes | Path | str


class ImageProvider(ABC):
    # GPT Image 2 single-reference editing is the production default until a
    # provider has been explicitly capability-tested for multiple inputs.
    multi_reference_image_edit: bool = False
    multi_reference_image_edit_status: str = "UNVERIFIED"

    @abstractmethod
    def generate(self, *, prompt: str, output_path: Path | None = None, **kwargs: Any) -> ImageOutput:
        raise NotImplementedError

    @abstractmethod
    def edit_with_reference(
        self,
        *,
        reference_images: Sequence[ImageInput],
        prompt: str,
        output_path: Path | None = None,
        **kwargs: Any,
    ) -> ImageOutput:
        raise NotImplementedError


__all__ = ["ImageInput", "ImageOutput", "ImageProvider"]
