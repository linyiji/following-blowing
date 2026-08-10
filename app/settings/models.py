"""Typed models for the user-configurable API provider settings.

Only non-sensitive values belong in :class:`ApiSettings`.  API keys are kept in
the credential store and are joined with these settings only when a runtime
configuration is explicitly requested.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


DEFAULT_FAST_MODEL = "gpt-5.6-luna"
DEFAULT_MAIN_MODEL = "gpt-5.6-terra"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_FAST_TIMEOUT = 60
DEFAULT_MAIN_TIMEOUT = 120
DEFAULT_IMAGE_TIMEOUT = 180

TEAMO_PRESET = "teamorouter"
TEAMO_BASE_URL = "https://api.teamorouter.com/v1"


class ProviderPreset(str, Enum):
    """Supported settings presets.

    ``CUSTOM`` is intentionally permissive: it lets a user point the OpenAI
    compatible client at another provider without changing application code.
    """

    CUSTOM = "custom"
    TEAMO = TEAMO_PRESET


class ApiSettings(BaseModel):
    """Persistable, non-sensitive provider settings.

    The model deliberately has no API-key field and rejects unknown fields, so
    accidentally passing a credential into the JSON repository fails closed.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        use_enum_values=True,
    )

    schema_version: Literal[1] = 1
    preset: ProviderPreset = ProviderPreset.CUSTOM
    provider: Literal["openai", "openai_compatible"] = "openai_compatible"
    base_url: str | None = None
    model_fast: str = Field(default=DEFAULT_FAST_MODEL, min_length=1)
    model_main: str = Field(default=DEFAULT_MAIN_MODEL, min_length=1)
    image_model: str = Field(default=DEFAULT_IMAGE_MODEL, min_length=1)
    fast_timeout: int = Field(default=DEFAULT_FAST_TIMEOUT, gt=0, le=3600)
    main_timeout: int = Field(default=DEFAULT_MAIN_TIMEOUT, gt=0, le=3600)
    image_timeout: int = Field(default=DEFAULT_IMAGE_TIMEOUT, gt=0, le=3600)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        candidate = value.strip().rstrip("/")
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not contain credentials")
        return candidate

    @property
    def fast_model(self) -> str:
        """Compatibility alias for clients using the route-first spelling."""

        return self.model_fast

    @property
    def main_model(self) -> str:
        """Compatibility alias for clients using the route-first spelling."""

        return self.model_main


class CredentialStatus(BaseModel):
    """Safe credential metadata returned to UI and controller callers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configured: bool
    persistent: bool = False
    backend: Literal["keyring", "session", "none"] = "none"

    @property
    def has_api_key(self) -> bool:
        return self.configured


class RuntimeProviderConfig(BaseModel):
    """Complete settings used internally while constructing API clients.

    ``api_key`` is excluded from serialization and repr output.  Code that
    genuinely needs the raw value must call :meth:`api_key_value` explicitly.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["openai", "openai_compatible"]
    base_url: str | None
    model_fast: str
    model_main: str
    image_model: str
    fast_timeout: int = Field(gt=0, le=3600)
    main_timeout: int = Field(gt=0, le=3600)
    image_timeout: int = Field(gt=0, le=3600)
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    credential_backend: Literal["keyring", "session", "none"] = "none"

    @property
    def fast_model(self) -> str:
        return self.model_fast

    @property
    def main_model(self) -> str:
        return self.model_main

    @property
    def has_api_key(self) -> bool:
        return self.api_key is not None

    def api_key_value(self) -> str | None:
        """Return the secret for the API client boundary only."""

        return self.api_key.get_secret_value() if self.api_key else None

    def public_view(self) -> dict[str, object]:
        """Return runtime metadata that is always safe to expose."""

        return {
            **self.model_dump(mode="json"),
            "credential_configured": self.has_api_key,
        }


class ApiSettingsSnapshot(BaseModel):
    """Safe result returned when the settings screen is opened or reopened."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    settings: ApiSettings
    credential: CredentialStatus


# Stable aliases for callers that use the longer product-oriented names.
ProviderSettingsProfile = ApiSettings
APISettings = ApiSettings
