from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping, Sequence


ImageInput = bytes | Path | str


class AIProvider(ABC):
    @abstractmethod
    def analyze_multimodal(
        self,
        *,
        images: Sequence[ImageInput],
        prompt: str,
        response_model: type | None = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def generate_text(
        self,
        *,
        prompt: str,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        raise NotImplementedError


__all__ = ["AIProvider", "ImageInput"]
