"""Opt-in GPT Image 2 edit/generation smoke tests.

This script never runs from pytest and never prints credentials or provider
URLs.  Run the single-reference edit first; generation is gated on its PASS
marker so the intended validation order cannot be skipped accidentally.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import FAST_MODEL, IMAGE_MODEL, MAIN_MODEL, load_settings  # noqa: E402
from app.providers import DemoImageProvider, OpenAIImageProvider, create_image_provider  # noqa: E402
from app.providers.image_artifact import ImageArtifact  # noqa: E402


SMOKE_ROOT = PROJECT_ROOT / "data" / "smoke"
EDIT_OUTPUT = SMOKE_ROOT / "gpt-image-2-single-edit.png"
GENERATION_OUTPUT = SMOKE_ROOT / "gpt-image-2-generation.png"
EDIT_MARKER = SMOKE_ROOT / "gpt-image-2-single-edit.json"
GENERATION_MARKER = SMOKE_ROOT / "gpt-image-2-generation.json"
VERIFICATION_MARKER = SMOKE_ROOT / "image-provider-verification.json"
IP_REFERENCE = PROJECT_ROOT / "assets" / "demo" / "ip_reference.jpg"


EDIT_PROMPT = """Edit only the supplied IP image. Add a simple small red employee hat
with one subtle yellow detail. Preserve the original silhouette, full head/body
relationship, ear structure, eye structure, nose and mouth, body proportions,
and the original minimal black line-art language. Keep the character immediately
recognizable as the same original IP. Do not create a fluffy redesign, realistic
dog, 3D render, new body structure, new facial structure, or large style change."""

GENERATION_PROMPT = """Create a low-complexity flat graphic on a clean white background:
one simple red employee cap with one tiny yellow badge, crisp minimal shapes,
no character, no text, no realism, no 3D."""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _safe_artifact_payload(artifact: ImageArtifact) -> dict[str, Any]:
    payload = artifact.model_dump(mode="json")
    payload["local_path"] = str(artifact.absolute_path.relative_to(PROJECT_ROOT))
    return payload


def _marker_matches(marker: dict[str, Any], output: Path, model: str) -> bool:
    if marker.get("status") != "PASS" or marker.get("model") != model:
        return False
    if not output.is_file() or output.stat().st_size <= 0:
        return False
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    artifact = marker.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("sha256") != digest:
        return False
    if marker.get("operation") == "edit":
        reference_hash = hashlib.sha256(IP_REFERENCE.read_bytes()).hexdigest()
        return marker.get("reference_sha256") == reference_hash
    return True


def _refresh_verification_marker(model: str, *, models_verified: bool) -> None:
    edit_ok = _marker_matches(_read_json(EDIT_MARKER), EDIT_OUTPUT, model)
    generation_ok = _marker_matches(
        _read_json(GENERATION_MARKER), GENERATION_OUTPUT, model
    )
    _write_json(
        VERIFICATION_MARKER,
        {
            "IMAGE_PROVIDER_VERIFIED": bool(
                models_verified and edit_ok and generation_ok
            ),
            "model": model,
            "models_endpoint_verified": models_verified,
            "single_reference_edit": "PASS" if edit_ok else "UNVERIFIED",
            "generation": "PASS" if generation_ok else "UNVERIFIED",
            "MULTI_REFERENCE_IMAGE_EDIT": "UNVERIFIED",
            "verified_at": (
                datetime.now(timezone.utc).isoformat()
                if models_verified and edit_ok and generation_ok
                else None
            ),
        },
    )


def _load_real_provider() -> tuple[Any, OpenAIImageProvider] | None:
    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    secrets: dict[str, Any] = {}
    if secrets_path.is_file():
        secrets = tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    settings = load_settings(project_root=PROJECT_ROOT, secrets=secrets)
    if not settings.image.api_key:
        print("SKIP: IMAGE_API_KEY/OPENAI_API_KEY is not configured")
        return None
    provider = create_image_provider(settings)
    if settings.demo_mode or isinstance(provider, DemoImageProvider):
        print("SKIP: configured ImageProvider resolves to demo mode")
        return None
    if not isinstance(provider, OpenAIImageProvider):
        print("SKIP: configured ImageProvider is not the OpenAI production adapter")
        return None
    expected_routes = (FAST_MODEL, MAIN_MODEL, IMAGE_MODEL)
    actual_routes = (settings.model_fast, settings.model_main, settings.image_model)
    if actual_routes != expected_routes:
        raise AssertionError("Configured model routes do not match the fixed production routes")
    if provider.multi_reference_image_edit:
        raise AssertionError("Multi-reference image editing must remain disabled by default")
    return settings, provider


def _verify_model_slugs(provider: OpenAIImageProvider) -> None:
    sdk = provider._require_sdk()
    call = provider.provider_client.call("models.list", sdk.models.list)
    raw = call.value
    data = raw.get("data", []) if isinstance(raw, dict) else getattr(raw, "data", [])
    available = {
        str(item.get("id") if isinstance(item, dict) else getattr(item, "id", ""))
        for item in data
    }
    missing = {FAST_MODEL, MAIN_MODEL, IMAGE_MODEL} - available
    if missing:
        raise AssertionError("Required production model slugs were not all returned by GET /v1/models")


def _assert_smoke_artifact(artifact: ImageArtifact, expected: Path) -> None:
    if artifact.absolute_path != expected.resolve():
        raise AssertionError("ImageProvider did not materialize the requested smoke path")
    if artifact.format != "PNG" or artifact.mime_type != "image/png":
        raise AssertionError("Smoke response was not a valid PNG image")
    if len(artifact.sha256) != 64 or expected.stat().st_size <= 0:
        raise AssertionError("Smoke image hash or byte length is invalid")


def _run_edit(provider: OpenAIImageProvider) -> ImageArtifact:
    artifact = provider.edit_with_reference(
        reference_images=[IP_REFERENCE],
        prompt=EDIT_PROMPT,
        output_path=EDIT_OUTPUT,
        quality="low",
    )
    if not isinstance(artifact, ImageArtifact):
        raise AssertionError("ImageProvider did not return a normalized ImageArtifact")
    _assert_smoke_artifact(artifact, EDIT_OUTPUT)
    return artifact


def _run_generation(provider: OpenAIImageProvider, model: str) -> ImageArtifact:
    edit_marker = _read_json(EDIT_MARKER)
    if not _marker_matches(edit_marker, EDIT_OUTPUT, model):
        raise RuntimeError("Generation is gated: run --edit and obtain PASS first")
    artifact = provider.generate(
        prompt=GENERATION_PROMPT,
        output_path=GENERATION_OUTPUT,
        quality="low",
        size="1024x1024",
    )
    if not isinstance(artifact, ImageArtifact):
        raise AssertionError("ImageProvider did not return a normalized ImageArtifact")
    _assert_smoke_artifact(artifact, GENERATION_OUTPUT)
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--edit", action="store_true", help="run single-reference edit smoke")
    mode.add_argument("--generate", action="store_true", help="run generation smoke after edit PASS")
    args = parser.parse_args(argv)

    loaded = _load_real_provider()
    if loaded is None:
        return 0
    settings, provider = loaded
    operation = "edit" if args.edit else "generation"
    marker = EDIT_MARKER if args.edit else GENERATION_MARKER
    models_verified = False
    try:
        _verify_model_slugs(provider)
        models_verified = True
        artifact = (
            _run_edit(provider)
            if args.edit
            else _run_generation(provider, settings.image_model)
        )
    except Exception as exc:
        _write_json(
            marker,
            {
                "status": "FAIL",
                "operation": operation,
                "model": settings.image_model,
                "error_type": type(exc).__name__,
                "request_id": getattr(exc, "request_id", None),
            },
        )
        _refresh_verification_marker(
            settings.image_model, models_verified=models_verified
        )
        print(f"FAIL: GPT Image 2 {operation} smoke ({type(exc).__name__})")
        return 1

    payload = {
        "status": "PASS",
        "operation": operation,
        "model": settings.image_model,
        "artifact": _safe_artifact_payload(artifact),
        "MULTI_REFERENCE_IMAGE_EDIT": "UNVERIFIED",
    }
    if args.edit:
        payload["reference_sha256"] = hashlib.sha256(
            IP_REFERENCE.read_bytes()
        ).hexdigest()
    _write_json(marker, payload)
    _refresh_verification_marker(settings.image_model, models_verified=True)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
