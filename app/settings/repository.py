"""JSON persistence for non-sensitive API settings."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from pydantic import ValidationError

from .models import ApiSettings


class SettingsRepositoryError(RuntimeError):
    """Raised when persisted settings cannot be read or validated."""


def default_settings_path(
    *,
    home: Path | None = None,
    platform: str | None = None,
    app_directory: str = "Following blowing",
) -> Path:
    """Choose an OS-appropriate non-sensitive settings path.

    macOS uses Application Support as the preferred location.  ``home`` and
    ``platform`` are injectable to keep path tests isolated from the host.
    """

    explicit_path = os.environ.get("FOLLOWING_BLOWING_CONFIG_PATH")
    if explicit_path and home is None and platform is None:
        return Path(explicit_path).expanduser()

    user_home = Path.home() if home is None else Path(home)
    current_platform = sys.platform if platform is None else platform
    if current_platform == "darwin":
        return user_home / "Library" / "Application Support" / app_directory / "settings.json"

    xdg_root = os.environ.get("XDG_CONFIG_HOME")
    config_root = Path(xdg_root) if xdg_root else user_home / ".config"
    return config_root / "following-blowing" / "settings.json"


_SENSITIVE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "authorization",
    "credential",
    "credentials",
}


def _assert_non_sensitive(value: Any) -> None:
    """Defense in depth against adding credentials to the JSON schema later."""

    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _SENSITIVE_FIELD_NAMES or normalized.endswith("_api_key"):
                raise SettingsRepositoryError(
                    f"sensitive field {key!r} cannot be persisted in settings JSON"
                )
            _assert_non_sensitive(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _assert_non_sensitive(nested)


class SettingsRepository:
    """Atomic JSON repository containing only :class:`ApiSettings`."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else default_settings_path()

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> ApiSettings:
        if not self.exists:
            return ApiSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            _assert_non_sensitive(raw)
            return ApiSettings.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError, TypeError) as exc:
            raise SettingsRepositoryError(
                f"settings file is unreadable or invalid: {self.path}"
            ) from exc

    def save(self, settings: ApiSettings | Mapping[str, Any]) -> ApiSettings:
        try:
            validated = (
                settings
                if isinstance(settings, ApiSettings)
                else ApiSettings.model_validate(settings)
            )
        except ValidationError as exc:
            raise SettingsRepositoryError("settings failed validation") from exc

        payload = validated.model_dump(mode="json")
        _assert_non_sensitive(payload)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.chmod(temporary_path, 0o600)
            temporary_path.replace(self.path)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise SettingsRepositoryError(f"could not save settings: {self.path}") from exc
        return validated

    def delete(self) -> bool:
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise SettingsRepositoryError(f"could not delete settings: {self.path}") from exc


JsonSettingsRepository = SettingsRepository
APISettingsRepository = SettingsRepository
