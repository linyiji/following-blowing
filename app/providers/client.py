from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any, Callable, Generic, Mapping, TypeVar

from app.errors import ProviderError as WorkflowProviderError
from app.services.errors import ProviderError


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ProviderCallMetadata:
    request_id: str
    operation: str
    attempt_count: int
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProviderCallResult(Generic[T]):
    value: T
    metadata: ProviderCallMetadata


def _usage_from(value: Any) -> tuple[int, int]:
    usage = getattr(value, "usage", None)
    if usage is None and isinstance(value, Mapping):
        usage = value.get("usage")
    if usage is None:
        return 0, 0
    if isinstance(usage, Mapping):
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
    else:
        input_tokens = getattr(usage, "input_tokens", getattr(usage, "prompt_tokens", 0))
        output_tokens = getattr(usage, "output_tokens", getattr(usage, "completion_tokens", 0))
    try:
        return int(input_tokens or 0), int(output_tokens or 0)
    except (TypeError, ValueError):
        return 0, 0


class ProviderClient:
    """Central retry/latency/request-id governance for provider adapters.

    Provider-specific SDK timeouts are configured by adapters; this class keeps
    retry policy and normalized errors out of agents.
    """

    def __init__(
        self,
        *,
        timeout: int = 120,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
        cost_estimator: Callable[[str, int, int], float] | None = None,
    ) -> None:
        if timeout <= 0 or max_retries < 0 or backoff_seconds < 0:
            raise ValueError("Invalid provider client governance settings")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._cost_estimator = cost_estimator
        self._records: list[ProviderCallMetadata] = []
        self._lock = RLock()

    @property
    def records(self) -> tuple[ProviderCallMetadata, ...]:
        with self._lock:
            return tuple(self._records)

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, WorkflowProviderError):
            return bool(getattr(exc, "retryable", False))
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        status = getattr(exc, "status_code", None)
        return status in {408, 409, 429} or isinstance(status, int) and status >= 500

    def call(self, operation: str, function: Callable[..., T], *args: Any, **kwargs: Any) -> ProviderCallResult[T]:
        request_id = f"req_{uuid.uuid4().hex}"
        started = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            try:
                value = function(*args, **kwargs)
                break
            except Exception as exc:
                if attempts > self.max_retries or not self._retryable(exc):
                    if isinstance(exc, WorkflowProviderError):
                        if getattr(exc, "request_id", None) is None:
                            exc.request_id = request_id  # type: ignore[attr-defined]
                            if hasattr(exc, "context"):
                                exc.context.setdefault("request_id", request_id)
                        raise
                    # Avoid echoing provider payloads, credentials, or URLs from
                    # arbitrary exception messages.
                    raise ProviderError(
                        f"{operation} failed ({type(exc).__name__})",
                        request_id=request_id,
                        retryable=False,
                    ) from exc
                delay = min(5.0, self.backoff_seconds * (2 ** (attempts - 1)))
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is not None:
                    try:
                        delay = min(10.0, max(delay, float(retry_after)))
                    except (TypeError, ValueError):
                        pass
                self._sleep(delay)

        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        input_tokens, output_tokens = _usage_from(value)
        estimated_cost = (
            float(self._cost_estimator(operation, input_tokens, output_tokens))
            if self._cost_estimator
            else 0.0
        )
        metadata = ProviderCallMetadata(
            request_id=request_id,
            operation=operation,
            attempt_count=attempts,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=estimated_cost,
        )
        with self._lock:
            self._records.append(metadata)
        return ProviderCallResult(value=value, metadata=metadata)

    def execute(self, operation: str, function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        return self.call(operation, function, *args, **kwargs).value


__all__ = ["ProviderCallMetadata", "ProviderCallResult", "ProviderClient"]
