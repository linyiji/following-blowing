"""Versioned Markdown prompt loading and trace metadata."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
REQUIRED_FRONT_MATTER = ("prompt_id", "version", "model_route", "output_schema")


@dataclass(frozen=True)
class PromptSpec:
    prompt_id: str
    version: str
    model_route: str
    output_schema: str
    body: str
    prompt_hash: str


def load_prompt(prompt_id: str) -> PromptSpec:
    """Load one prompt and validate its minimal auditable front matter."""

    normalized = prompt_id.strip().lower().replace("-", "_")
    if not normalized or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in normalized):
        raise ValueError("Invalid prompt_id")
    path = PROMPT_DIR / f"{normalized}.md"
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Prompt front matter is missing: {normalized}")
    try:
        closing = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"Prompt front matter is not closed: {normalized}") from exc
    metadata: dict[str, str] = {}
    for line in lines[1:closing]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"Invalid prompt front matter line: {line}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip("\"'")
    missing = [key for key in REQUIRED_FRONT_MATTER if not metadata.get(key)]
    if missing:
        raise ValueError(f"Prompt front matter missing fields: {missing}")
    if metadata["prompt_id"] != normalized:
        raise ValueError(
            f"Prompt id mismatch: expected {normalized}, found {metadata['prompt_id']}"
        )
    if metadata["model_route"] not in {"fast", "main", "image"}:
        raise ValueError(f"Unsupported prompt model route: {metadata['model_route']}")
    body = "\n".join(lines[closing + 1 :]).strip()
    if not body:
        raise ValueError(f"Prompt body is empty: {normalized}")
    return PromptSpec(
        prompt_id=metadata["prompt_id"],
        version=metadata["version"],
        model_route=metadata["model_route"],
        output_schema=metadata["output_schema"],
        body=body,
        prompt_hash=sha256(raw.encode("utf-8")).hexdigest(),
    )


__all__ = ["PROMPT_DIR", "PromptSpec", "load_prompt"]
