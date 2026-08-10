"""Application configuration.

Configuration is loaded on the Python side only.  Public health/status payloads
must use :meth:`AppSettings.public_status`, which deliberately never includes
credentials.
"""

from __future__ import annotations

import os
import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from app.settings.models import RuntimeProviderConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "Following blowing"
FORMER_PROJECT_NAME = "ai-ip-brand"
FAST_MODEL = "gpt-5.6-luna"
MAIN_MODEL = "gpt-5.6-terra"
IMAGE_MODEL = "gpt-image-2"
COMPETITION_MODE = True
MULTI_REFERENCE_IMAGE_EDIT = False
# Environment/secrets keys use MODEL_FAST / MODEL_MAIN. Keep both spellings
# explicit because provider code and deployment configuration have different conventions.
MODEL_FAST = FAST_MODEL
MODEL_MAIN = MAIN_MODEL


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read a small .env file without making python-dotenv mandatory."""

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        # Configuration remains usable from environment variables when PyYAML
        # is unavailable.  Do not implement a permissive, unsafe YAML parser.
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _secret_value(secrets: Mapping[str, Any] | None, key: str) -> str | None:
    if not secrets:
        return None
    value = secrets.get(key)
    if value in (None, ""):
        return None
    return str(value)


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    provider: str = "demo"
    base_url: str | None = None
    model: str | None = None
    timeout: int = 120
    api_key: str | None = field(default=None, repr=False, compare=False)

    @property
    def is_demo(self) -> bool:
        return self.provider.strip().lower() in {"demo", "mock", "none", ""}

    @property
    def configured(self) -> bool:
        return self.is_demo or bool(self.api_key and self.model)

    def public_status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url_configured": bool(self.base_url),
            "model": self.model,
            "timeout": self.timeout,
            "configured": self.configured,
        }


@dataclass(frozen=True, slots=True)
class AppSettings:
    project_root: Path
    multimodal: ProviderSettings
    image: ProviderSettings
    search: ProviderSettings
    model_fast: str = MODEL_FAST
    model_main: str = MODEL_MAIN
    image_model: str = IMAGE_MODEL
    document_parser: str = "local"
    demo_mode: bool = True
    demo_explicit: bool = False
    app_name: str = APP_NAME
    competition_mode: bool = COMPETITION_MODE
    search_provider_verified: bool = False
    image_provider_verified: bool = False
    model_catalog_verified: bool = False
    multi_reference_image_edit: bool = MULTI_REFERENCE_IMAGE_EDIT
    multi_reference_image_edit_verified: bool = False
    max_guardian_retries: int = 2
    max_image_generations_per_run: int = 3
    max_ai_supplement_retries: int = 3
    max_provider_retries: int = 2
    fast_timeout: int = 60
    main_timeout: int = 120
    image_timeout: int = 180
    provider_source: str = "demo"
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def provider_mode(self) -> str:
        return "demo" if self.demo_mode else "live"

    @property
    def search_mode(self) -> str:
        if self.demo_mode or self.search.is_demo:
            return "demo"
        if self.search.configured and self.search_provider_verified:
            return "live"
        return "unverified"

    @property
    def multi_reference_image_edit_status(self) -> str:
        if self.multi_reference_image_edit and self.multi_reference_image_edit_verified:
            return "VERIFIED"
        return "UNVERIFIED"

    @property
    def allow_multi_reference_image_edit(self) -> bool:
        return (
            self.multi_reference_image_edit
            and self.multi_reference_image_edit_verified
        )

    def public_status(self) -> dict[str, Any]:
        """Return configuration suitable for UI/health output (never secrets)."""

        return {
            "app_name": self.app_name,
            "demo_mode": self.demo_mode,
            "demo_explicit": self.demo_explicit,
            "competition_mode": self.competition_mode,
            "provider_mode": self.provider_mode,
            "provider_source": self.provider_source,
            "search_mode": self.search_mode,
            "image_provider_verified": self.image_provider_verified,
            "model_catalog_verified": self.model_catalog_verified,
            "multi_reference_image_edit": self.allow_multi_reference_image_edit,
            "multi_reference_image_edit_status": self.multi_reference_image_edit_status,
            "multimodal": self.multimodal.public_status(),
            "image": self.image.public_status(),
            "search": self.search.public_status(),
            "model_routes": {
                "fast": self.model_fast,
                "main": self.model_main,
                "image": self.image_model,
            },
            "timeouts": {
                "fast": self.fast_timeout,
                "main": self.main_timeout,
                "image": self.image_timeout,
            },
            "document_parser": self.document_parser,
            "limits": {
                "max_guardian_retries": self.max_guardian_retries,
                "max_image_generations_per_run": self.max_image_generations_per_run,
                "max_ai_supplement_retries": self.max_ai_supplement_retries,
                "max_provider_retries": self.max_provider_retries,
            },
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_image_marker(data_dir: Path, model: str) -> bool:
    """Validate the local, non-secret acceptance record written by real smoke tests."""

    marker = data_dir / "smoke" / "image-provider-verification.json"
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False
    if not isinstance(value, Mapping):
        return False
    if (
        value.get("IMAGE_PROVIDER_VERIFIED") is not True
        or value.get("model") != model
        or value.get("models_endpoint_verified") is not True
    ):
        return False
    operation_markers = (
        data_dir / "smoke" / "gpt-image-2-single-edit.json",
        data_dir / "smoke" / "gpt-image-2-generation.json",
    )
    for operation_marker in operation_markers:
        try:
            record = json.loads(operation_marker.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return False
        if not isinstance(record, Mapping) or record.get("status") != "PASS":
            return False
        if record.get("model") != model:
            return False
        artifact_record = record.get("artifact")
        if not isinstance(artifact_record, Mapping):
            return False
        relative = Path(str(artifact_record.get("local_path") or ""))
        expected_hash = str(artifact_record.get("sha256") or "")
        if relative.is_absolute() or ".." in relative.parts or not expected_hash:
            return False
        artifact = (data_dir.parent / relative).resolve()
        try:
            artifact.relative_to(data_dir.parent.resolve())
            if not artifact.is_file() or _sha256_file(artifact) != expected_hash:
                return False
        except (OSError, ValueError):
            return False
    return True


def _verified_model_catalog_marker(data_dir: Path, model: str) -> bool:
    marker = data_dir / "smoke" / "image-provider-verification.json"
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(value, Mapping)
        and value.get("model") == model
        and value.get("models_endpoint_verified") is True
    )


def _provider_settings(
    section: str,
    yaml_config: Mapping[str, Any],
    values: Mapping[str, str],
    secrets: Mapping[str, Any] | None,
) -> ProviderSettings:
    section_config = yaml_config.get(section, {})
    if not isinstance(section_config, Mapping):
        section_config = {}
    prefix = "IMAGE" if section == "image" else section.upper()
    provider = values.get(f"{prefix}_PROVIDER", str(section_config.get("provider", "demo")))
    base_url = values.get(f"{prefix}_BASE_URL") or section_config.get("base_url")
    model = values.get(f"{prefix}_MODEL") or section_config.get("model")
    timeout_default = 180 if section == "image" else 120
    timeout = _as_int(
        values.get(f"{prefix}_TIMEOUT", section_config.get("timeout")),
        timeout_default,
    )
    key_name = f"{prefix}_API_KEY"
    api_key = values.get(key_name) or _secret_value(secrets, key_name)
    # OpenAI adapters may share the conventional server-side key.
    if not api_key and str(provider).lower() == "openai":
        api_key = values.get("OPENAI_API_KEY") or _secret_value(secrets, "OPENAI_API_KEY")
    return ProviderSettings(
        provider=str(provider),
        base_url=str(base_url) if base_url else None,
        model=str(model) if model else None,
        timeout=max(1, timeout),
        api_key=api_key,
    )


def load_settings(
    *,
    environ: Mapping[str, str] | None = None,
    secrets: Mapping[str, Any] | None = None,
    project_root: Path | str | None = None,
) -> AppSettings:
    """Load settings with precedence: environment, secrets, .env, YAML.

    Streamlit callers may explicitly pass top-level ``st.secrets`` values so a
    Community Cloud deployment can select providers without committing a
    provider configuration change.  This module never imports Streamlit or
    serializes secret values to a browser-facing object.
    """

    root = Path(project_root).resolve() if project_root else PROJECT_ROOT
    dotenv_values = _read_dotenv(root / ".env")
    env_values = dict(dotenv_values)
    if secrets:
        env_values.update(
            {
                str(key): str(value)
                for key, value in secrets.items()
                if value is not None and isinstance(value, (str, int, float, bool))
            }
        )
    env_values.update(dict(os.environ if environ is None else environ))
    yaml_config = _load_yaml(root / "config" / "providers.yaml")

    multimodal = _provider_settings("multimodal", yaml_config, env_values, secrets)
    image = _provider_settings("image", yaml_config, env_values, secrets)
    search = _provider_settings("search", yaml_config, env_values, secrets)
    models_config = yaml_config.get("models", {})
    if not isinstance(models_config, Mapping):
        models_config = {}
    model_fast = str(env_values.get("MODEL_FAST") or models_config.get("fast") or MODEL_FAST)
    model_main = str(
        env_values.get("MODEL_MAIN")
        or multimodal.model
        or models_config.get("main")
        or MODEL_MAIN
    )
    image_model = str(
        env_values.get("IMAGE_MODEL")
        or image.model
        or models_config.get("image")
        or IMAGE_MODEL
    )
    # Keep legacy ProviderSettings consumers configured while all text/vision
    # calls route explicitly through model_fast or model_main.
    multimodal = replace(multimodal, model=model_main)
    image = replace(image, model=image_model)

    explicit_demo = env_values.get("DEMO_MODE")
    automatically_demo = (
        multimodal.is_demo
        or image.is_demo
        or not (multimodal.configured and image.configured)
    )
    demo_mode = _as_bool(explicit_demo, automatically_demo)

    application_config = yaml_config.get("application", {})
    if not isinstance(application_config, Mapping):
        application_config = {}
    document_config = yaml_config.get("document", {})
    if not isinstance(document_config, Mapping):
        document_config = {}
    data_dir_value = env_values.get("DATA_DIR")
    data_dir = Path(data_dir_value).expanduser() if data_dir_value else root / "data"
    if not data_dir.is_absolute():
        data_dir = root / data_dir
    data_dir = data_dir.resolve()

    app_name = str(
        env_values.get("APP_NAME")
        or application_config.get("app_name")
        or APP_NAME
    )
    competition_mode = _as_bool(
        env_values.get("COMPETITION_MODE", application_config.get("competition_mode")),
        COMPETITION_MODE,
    )
    search_provider_verified = _as_bool(
        env_values.get(
            "SEARCH_PROVIDER_VERIFIED",
            application_config.get("search_provider_verified"),
        ),
        False,
    )
    multi_reference_image_edit = _as_bool(
        env_values.get(
            "MULTI_REFERENCE_IMAGE_EDIT",
            application_config.get("multi_reference_image_edit"),
        ),
        MULTI_REFERENCE_IMAGE_EDIT,
    )
    multi_reference_image_edit_verified = _as_bool(
        env_values.get(
            "MULTI_REFERENCE_IMAGE_EDIT_VERIFIED",
            application_config.get("multi_reference_image_edit_verified"),
        ),
        False,
    )
    explicit_image_verified = env_values.get("IMAGE_PROVIDER_VERIFIED")
    marker_verified = _verified_image_marker(data_dir, image_model)
    model_catalog_verified = _verified_model_catalog_marker(data_dir, image_model)
    # A boolean setting may disable a stale acceptance, but cannot promote an
    # untested adapter. Real readiness comes only from the hash-validated smoke
    # record written after both edit and generation pass.
    image_provider_verified = marker_verified and _as_bool(
        explicit_image_verified,
        True,
    )

    return AppSettings(
        project_root=root,
        multimodal=multimodal,
        image=image,
        search=search,
        model_fast=model_fast,
        model_main=model_main,
        image_model=image_model,
        document_parser=str(document_config.get("parser", "local")),
        demo_mode=demo_mode,
        demo_explicit=(explicit_demo is not None and _as_bool(explicit_demo)),
        app_name=app_name,
        competition_mode=competition_mode,
        search_provider_verified=search_provider_verified,
        image_provider_verified=image_provider_verified,
        model_catalog_verified=model_catalog_verified,
        multi_reference_image_edit=multi_reference_image_edit,
        multi_reference_image_edit_verified=multi_reference_image_edit_verified,
        max_guardian_retries=max(0, _as_int(env_values.get("MAX_GUARDIAN_RETRIES"), 2)),
        max_image_generations_per_run=max(
            1, _as_int(env_values.get("MAX_IMAGE_GENERATIONS_PER_RUN"), 3)
        ),
        max_ai_supplement_retries=max(
            0, _as_int(env_values.get("MAX_AI_SUPPLEMENT_RETRIES"), 3)
        ),
        max_provider_retries=max(0, _as_int(env_values.get("MAX_PROVIDER_RETRIES"), 2)),
        fast_timeout=max(1, _as_int(env_values.get("FAST_TIMEOUT"), 60)),
        main_timeout=max(1, multimodal.timeout),
        image_timeout=max(1, image.timeout),
        provider_source=("demo" if demo_mode else "admin"),
        data_dir=data_dir,
    )


def apply_runtime_provider_config(
    settings: AppSettings,
    runtime: "RuntimeProviderConfig",
) -> AppSettings:
    """Overlay a user's BYOK configuration on administrator/default settings.

    This is the only bridge where a credential-bearing runtime object becomes
    provider settings.  The returned :class:`AppSettings` still redacts the key
    from repr/public serialization through :class:`ProviderSettings`.
    Search deliberately remains Demo/Mock for the BYOK edition.
    """

    api_key_getter = getattr(runtime, "api_key_value", None)
    api_key = api_key_getter() if callable(api_key_getter) else None
    if not api_key:
        raise ValueError("Runtime provider configuration has no API credential")

    raw_provider = str(getattr(runtime, "provider", "openai")).strip().lower()
    supported = {
        "openai",
        "openai compatible",
        "openai-compatible",
        "openai_compatible",
        "custom",
        "teamorouter",
    }
    if raw_provider not in supported:
        raise ValueError("Unsupported OpenAI-compatible provider")

    base_url = getattr(runtime, "base_url", None)
    model_fast = str(getattr(runtime, "model_fast"))
    model_main = str(getattr(runtime, "model_main"))
    image_model = str(getattr(runtime, "image_model"))
    fast_timeout = max(1, int(getattr(runtime, "fast_timeout", 60)))
    main_timeout = max(1, int(getattr(runtime, "main_timeout", 120)))
    image_timeout = max(1, int(getattr(runtime, "image_timeout", 180)))

    return replace(
        settings,
        multimodal=ProviderSettings(
            provider="openai",
            base_url=str(base_url) if base_url else None,
            model=model_main,
            timeout=main_timeout,
            api_key=api_key,
        ),
        image=ProviderSettings(
            provider="openai",
            base_url=str(base_url) if base_url else None,
            model=image_model,
            timeout=image_timeout,
            api_key=api_key,
        ),
        # Search settings are intentionally not part of this BYOK surface.
        search=ProviderSettings(provider="demo", timeout=main_timeout),
        model_fast=model_fast,
        model_main=model_main,
        image_model=image_model,
        fast_timeout=fast_timeout,
        main_timeout=main_timeout,
        image_timeout=image_timeout,
        demo_mode=False,
        demo_explicit=False,
        provider_source="byok",
        # A BYOK model-catalog check is non-persistent session health, not an
        # historical image-generation acceptance marker.
        model_catalog_verified=False,
        image_provider_verified=False,
    )


__all__ = [
    "PROJECT_ROOT",
    "APP_NAME",
    "FORMER_PROJECT_NAME",
    "FAST_MODEL",
    "MAIN_MODEL",
    "MODEL_FAST",
    "MODEL_MAIN",
    "IMAGE_MODEL",
    "COMPETITION_MODE",
    "MULTI_REFERENCE_IMAGE_EDIT",
    "AppSettings",
    "ProviderSettings",
    "apply_runtime_provider_config",
    "load_settings",
]
