from __future__ import annotations

import base64
import shutil
from pathlib import Path
from typing import Any, Sequence

from app.config import PROJECT_ROOT

from .image_artifact import normalize_image_artifact
from .image_base import ImageInput, ImageOutput, ImageProvider


# A valid 1x1 RGBA PNG used only when no project demo result is available.
_FALLBACK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class DemoImageProvider(ImageProvider):
    def __init__(self, fixture_path: Path | str | None = None, *, output_root: Path | str | None = None) -> None:
        self.fixture_path = Path(fixture_path).resolve() if fixture_path else self._find_fixture()
        self.output_root = Path(output_root or PROJECT_ROOT / "data" / "generated").resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _find_fixture() -> Path | None:
        demo_root = PROJECT_ROOT / "assets" / "demo"
        for pattern in ("final_result.png", "final_result.jpg", "final_result.jpeg", "final_result.webp"):
            candidate = demo_root / pattern
            if candidate.is_file():
                return candidate.resolve()
        return None

    def generate(self, *, prompt: str, output_path: Path | None = None, **kwargs: Any) -> ImageOutput:
        del prompt, kwargs
        destination = Path(output_path or self.output_root / "demo_result.png").resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if self.fixture_path and self.fixture_path.is_file():
            shutil.copyfile(self.fixture_path, destination)
        else:
            destination.write_bytes(_FALLBACK_PNG)
        return normalize_image_artifact(
            destination,
            relative_to=PROJECT_ROOT,
            provider="demo",
            model="demo-image-fixture",
        )

    def edit_with_reference(
        self,
        *,
        reference_images: Sequence[ImageInput],
        prompt: str,
        output_path: Path | None = None,
        **kwargs: Any,
    ) -> ImageOutput:
        del reference_images
        return self.generate(prompt=prompt, output_path=output_path, **kwargs)


__all__ = ["DemoImageProvider"]
