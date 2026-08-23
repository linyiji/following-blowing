"""Application service for BYOK provider settings."""

from __future__ import annotations

from collections.abc import Mapping
from threading import RLock
from typing import Any

from pydantic import SecretStr

from .credential_store import CredentialStore
from .models import (
    DEFAULT_FAST_MODEL,
    DEFAULT_IMAGE_MODEL,
    DEFAULT_MAIN_MODEL,
    TEAMO_BASE_URL,
    TEAMO_PRESET,
    ApiSettings,
    ApiSettingsSnapshot,
    CredentialStatus,
    RuntimeProviderConfig,
)
from .repository import SettingsRepository


class UnsupportedProviderPreset(ValueError):
    """Raised when an unknown provider preset is requested."""


class CredentialNotConfiguredError(RuntimeError):
    """Raised when live runtime settings require a missing API key."""


class APISettingsService:
    """Coordinates safe JSON settings and separately stored credentials."""

    def __init__(
        self,
        repository: SettingsRepository | None = None,
        credential_store: CredentialStore | None = None,
    ) -> None:
        self.repository = repository or SettingsRepository()
        self.credential_store = credential_store or CredentialStore()
        self._lock = RLock()
        # One-shot, server-memory-only handoff from a successful connection
        # test to an explicit save action. It is never serialized or exposed
        # through public/session UI state.
        self._verified_settings: ApiSettings | None = None
        self._verified_api_key: SecretStr | None = None

    def stage_verified_credential(
        self,
        settings: ApiSettings | Mapping[str, Any],
        api_key: str | SecretStr,
    ) -> None:
        """Remember a successfully tested key until the next matching save."""

        normalized = self._normalize_settings(settings)
        raw_value = (
            api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        )
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("Verified API key must not be blank")
        with self._lock:
            self._verified_settings = normalized
            self._verified_api_key = SecretStr(raw_value.strip())

    def clear_verified_credential(self) -> None:
        with self._lock:
            self._verified_settings = None
            self._verified_api_key = None

    def consume_verified_credential(
        self,
        settings: ApiSettings | Mapping[str, Any],
    ) -> str | None:
        """Consume the tested key only when the exact tested settings match."""

        normalized = self._normalize_settings(settings)
        with self._lock:
            if (
                self._verified_settings != normalized
                or self._verified_api_key is None
            ):
                return None
            secret = self._verified_api_key.get_secret_value()
            self._verified_settings = None
            self._verified_api_key = None
            return secret

    def load(self) -> ApiSettings:
        """Load only non-sensitive provider settings."""

        return self.repository.load()

    def credential_status(self) -> CredentialStatus:
        """Return presence/storage metadata, never the key itself."""

        return self.credential_store.status()

    status = credential_status

    def public(self) -> ApiSettingsSnapshot:
        """Return the complete settings-screen payload without credentials."""

        return ApiSettingsSnapshot(
            settings=self.load(),
            credential=self.credential_status(),
        )

    def public_view(self) -> dict[str, object]:
        """Return a flat, JSON-safe form payload with no credential value."""

        settings = self.load()
        credential = self.credential_status()
        session_only = credential.configured and not credential.persistent
        warning = (
            "API key is stored for this session only; the system keyring is unavailable."
            if session_only
            else None
        )
        return {
            **settings.model_dump(mode="json"),
            "credential_configured": credential.configured,
            "credential_persistent": credential.persistent,
            "credential_backend": credential.backend,
            "session_only": session_only,
            "storage_warning": warning,
        }

    def reopen(self) -> ApiSettingsSnapshot:
        """Reload the settings screen; the result can never serialize a key."""

        return self.public()

    def save(
        self,
        settings: ApiSettings | Mapping[str, Any],
        *,
        api_key: str | SecretStr | None = None,
        persist_credential: bool = True,
    ) -> ApiSettingsSnapshot:
        """Save settings and, when supplied, route a key to secure storage.

        ``api_key=None`` leaves the existing credential untouched.  Credentials
        are never added to the repository payload.
        """

        with self._lock:
            self.repository.save(self._normalize_settings(settings))
            if api_key is not None:
                self.save_api_key(api_key, persistent=persist_credential)
            return self.public()

    save_settings = save

    @staticmethod
    def _normalize_settings(
        settings: ApiSettings | Mapping[str, Any],
    ) -> ApiSettings:
        """Accept both flat form fields and a nested ``timeouts`` payload."""

        if isinstance(settings, ApiSettings):
            return settings
        payload = dict(settings)
        timeouts = payload.pop("timeouts", None)
        if timeouts is not None:
            if not isinstance(timeouts, Mapping):
                raise ValueError("timeouts must be an object")
            aliases = {
                "fast": "fast_timeout",
                "main": "main_timeout",
                "image": "image_timeout",
                "fast_timeout": "fast_timeout",
                "main_timeout": "main_timeout",
                "image_timeout": "image_timeout",
            }
            for name, value in timeouts.items():
                target = aliases.get(str(name))
                if target is None:
                    raise ValueError(f"unsupported timeout route: {name}")
                if target in payload and payload[target] != value:
                    raise ValueError(f"conflicting timeout value for {target}")
                payload[target] = value
        return ApiSettings.model_validate(payload)

    def save_api_key(
        self,
        api_key: str | SecretStr,
        *,
        persistent: bool = True,
    ) -> CredentialStatus:
        raw_value = (
            api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        )
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("API key must not be blank")
        return self.credential_store.set_secret(
            raw_value.strip(),
            persistent=persistent,
        )

    def delete_credential(self) -> CredentialStatus:
        """Delete the configured key and return only safe status metadata."""

        return self.credential_store.delete()

    delete_api_key = delete_credential
    delete = delete_credential

    def preset(
        self,
        name: str = TEAMO_PRESET,
        *,
        save: bool = True,
    ) -> ApiSettingsSnapshot:
        """Apply a provider preset without reading, setting, or deleting a key."""

        normalized = name.strip().lower()
        if normalized not in {TEAMO_PRESET, "teamo", "teamo-router"}:
            raise UnsupportedProviderPreset(f"unsupported provider preset: {name}")

        current = self.load()
        updated = current.model_copy(
            update={
                "base_url": TEAMO_BASE_URL,
                "model_fast": DEFAULT_FAST_MODEL,
                "model_main": DEFAULT_MAIN_MODEL,
                "image_model": DEFAULT_IMAGE_MODEL,
            }
        )
        if save:
            self.repository.save(updated)
        return ApiSettingsSnapshot(
            settings=updated,
            credential=self.credential_status(),
        )

    apply_preset = preset

    def apply_teamo_preset(self, *, save: bool = True) -> ApiSettingsSnapshot:
        return self.preset(TEAMO_PRESET, save=save)

    def runtime_config(
        self,
        *,
        require_credential: bool = False,
    ) -> RuntimeProviderConfig:
        """Join safe settings and the key at the internal provider boundary."""

        settings = self.load()
        status = self.credential_status()
        secret = self.credential_store.get_secret()
        if require_credential and secret is None:
            raise CredentialNotConfiguredError("API key is not configured")
        return RuntimeProviderConfig(
            provider=settings.provider,
            base_url=settings.base_url,
            model_fast=settings.model_fast,
            model_main=settings.model_main,
            image_model=settings.image_model,
            fast_timeout=settings.fast_timeout,
            main_timeout=settings.main_timeout,
            image_timeout=settings.image_timeout,
            api_key=SecretStr(secret) if secret is not None else None,
            credential_backend=status.backend,
        )

    build_runtime_config = runtime_config


ApiSettingsService = APISettingsService
