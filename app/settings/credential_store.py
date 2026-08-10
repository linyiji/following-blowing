"""Secure API-key storage with an in-memory-only fallback.

The preferred backend is the operating system keyring.  If it is unavailable,
the key can remain usable for the current process, but it is never written to a
plaintext file or folded into the non-sensitive settings JSON.
"""

from __future__ import annotations

from threading import RLock
from typing import Any, Protocol, runtime_checkable

from .models import CredentialStatus


DEFAULT_KEYRING_SERVICE = "following-blowing"
DEFAULT_KEYRING_ACCOUNT = "provider-api-key"


class CredentialStoreUnavailable(RuntimeError):
    """Raised when a secure credential backend cannot be used."""


@runtime_checkable
class CredentialBackend(Protocol):
    """Backend contract used by the routing credential store."""

    backend_name: str
    persistent: bool

    def set_secret(self, secret: str) -> CredentialStatus: ...

    def get_secret(self) -> str | None: ...

    def status(self) -> CredentialStatus: ...

    def delete(self) -> CredentialStatus: ...


class SessionCredentialStore:
    """Process-memory credential storage used when persistence is unavailable."""

    backend_name = "session"
    persistent = False

    def __init__(self) -> None:
        self._secret: str | None = None
        self._lock = RLock()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(configured={self._secret is not None})"

    def set_secret(self, secret: str) -> CredentialStatus:
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError("API key must not be blank")
        with self._lock:
            self._secret = secret.strip()
        return self.status()

    def get_secret(self) -> str | None:
        with self._lock:
            return self._secret

    def status(self) -> CredentialStatus:
        with self._lock:
            configured = self._secret is not None
        return CredentialStatus(
            configured=configured,
            persistent=False,
            backend="session" if configured else "none",
        )

    def delete(self) -> CredentialStatus:
        with self._lock:
            self._secret = None
        return CredentialStatus(configured=False, persistent=False, backend="none")


class KeyringCredentialStore:
    """Credential backend backed by the system keyring.

    ``keyring_module`` is injectable for unit tests.  The real dependency is
    imported lazily so normal imports and tests never prompt the OS keychain.
    """

    backend_name = "keyring"
    persistent = True

    def __init__(
        self,
        *,
        service_name: str = DEFAULT_KEYRING_SERVICE,
        account_name: str = DEFAULT_KEYRING_ACCOUNT,
        keyring_module: Any | None = None,
    ) -> None:
        self.service_name = service_name
        self.account_name = account_name
        self._keyring_module = keyring_module

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(service_name={self.service_name!r}, "
            f"account_name={self.account_name!r})"
        )

    def _client(self) -> Any:
        if self._keyring_module is not None:
            return self._keyring_module
        try:
            import keyring
        except (ImportError, RuntimeError) as exc:
            raise CredentialStoreUnavailable("system keyring is unavailable") from exc
        self._keyring_module = keyring
        return keyring

    def set_secret(self, secret: str) -> CredentialStatus:
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError("API key must not be blank")
        try:
            self._client().set_password(
                self.service_name,
                self.account_name,
                secret.strip(),
            )
        except Exception as exc:
            raise CredentialStoreUnavailable("could not save API key to system keyring") from exc
        return CredentialStatus(configured=True, persistent=True, backend="keyring")

    def get_secret(self) -> str | None:
        try:
            value = self._client().get_password(self.service_name, self.account_name)
        except Exception as exc:
            raise CredentialStoreUnavailable("could not read API key from system keyring") from exc
        return value if isinstance(value, str) and value else None

    def status(self) -> CredentialStatus:
        configured = self.get_secret() is not None
        return CredentialStatus(
            configured=configured,
            persistent=configured,
            backend="keyring" if configured else "none",
        )

    def delete(self) -> CredentialStatus:
        try:
            client = self._client()
            if client.get_password(self.service_name, self.account_name) is not None:
                client.delete_password(self.service_name, self.account_name)
        except Exception as exc:
            raise CredentialStoreUnavailable("could not delete API key from system keyring") from exc
        return CredentialStatus(configured=False, persistent=False, backend="none")


class CredentialStore:
    """Prefer a secure keyring and fall back only to process memory."""

    def __init__(
        self,
        preferred: CredentialBackend | None = None,
        fallback: SessionCredentialStore | None = None,
    ) -> None:
        self._preferred = preferred or KeyringCredentialStore()
        self._fallback = fallback or SessionCredentialStore()
        self._active_backend: str | None = None
        self._lock = RLock()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(active_backend={self._active_backend!r})"

    def set_secret(self, secret: str, *, persistent: bool = True) -> CredentialStatus:
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError("API key must not be blank")
        with self._lock:
            if persistent:
                try:
                    status = self._preferred.set_secret(secret)
                    self._fallback.delete()
                    self._active_backend = "keyring"
                    return status
                except CredentialStoreUnavailable:
                    pass
            status = self._fallback.set_secret(secret)
            self._active_backend = "session"
            return status

    # ``save`` is a concise compatibility alias for form/controller callers.
    def save(self, secret: str, *, persistent: bool = True) -> CredentialStatus:
        return self.set_secret(secret, persistent=persistent)

    def _resolved_secret(self) -> tuple[str | None, str]:
        if self._active_backend == "session":
            session_secret = self._fallback.get_secret()
            if session_secret is not None:
                return session_secret, "session"

        try:
            preferred_secret = self._preferred.get_secret()
        except CredentialStoreUnavailable:
            preferred_secret = None
        if preferred_secret is not None:
            self._active_backend = "keyring"
            return preferred_secret, "keyring"

        session_secret = self._fallback.get_secret()
        if session_secret is not None:
            self._active_backend = "session"
            return session_secret, "session"
        self._active_backend = None
        return None, "none"

    def get_secret(self) -> str | None:
        """Return the key only for the runtime-provider boundary."""

        with self._lock:
            secret, _ = self._resolved_secret()
            return secret

    def status(self) -> CredentialStatus:
        with self._lock:
            secret, backend = self._resolved_secret()
            return CredentialStatus(
                configured=secret is not None,
                persistent=secret is not None and backend == "keyring",
                backend=backend,
            )

    def delete(self) -> CredentialStatus:
        with self._lock:
            try:
                self._preferred.delete()
            except CredentialStoreUnavailable:
                # The keyring cannot be inspected or mutated, but no secret is
                # copied out of it and the local session key is still cleared.
                pass
            self._fallback.delete()
            self._active_backend = None
            return CredentialStatus(configured=False, persistent=False, backend="none")

    delete_secret = delete


MemoryCredentialStore = SessionCredentialStore
