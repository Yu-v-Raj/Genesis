"""Genesis-facing LLM generation orchestration.

One ``generate`` call is one model request, made at most ``RetryPolicy.max_attempts`` times:

- Only failures marked ``retryable`` (rate limits, overload, broken connections, timeouts)
  are retried, after exponential backoff with jitter, or after the provider's Retry-After
  when it sent one (bounded). Configuration errors, invalid requests and unreadable
  responses fail at once.
- Every attempt, and every wait, fits inside one overall deadline; nothing waits forever.
- Cancellation is never retried or swallowed: it is recorded and re-raised.

Generating a reply has no side effects. Tools run in the Agent and Tool runtimes only
after a response is returned, so repeating a model request can never repeat a tool call
or use an approval twice. Providers are not switched automatically.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.exceptions import LLMRuntimeError, LLMTimeoutError, error_category
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse
from backend.app.core.observability.domain.events import LLMCompleted, LLMFailed, LLMRequested, LLMRetrying


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounds for one model request. The default makes a single attempt (no retries)."""

    max_attempts: int = 1
    base_delay: float = 0.5
    max_delay: float = 8.0
    total_timeout: float = 120.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.base_delay < 0 or self.max_delay < 0 or self.total_timeout <= 0:
            raise ValueError("Retry policy bounds must be positive.")

    @classmethod
    def from_settings(cls, settings: object) -> "RetryPolicy":
        return cls(
            max_attempts=getattr(settings, "LLM_MAX_ATTEMPTS"),
            base_delay=getattr(settings, "LLM_RETRY_BASE_DELAY_SECONDS"),
            max_delay=getattr(settings, "LLM_RETRY_MAX_DELAY_SECONDS"),
            total_timeout=getattr(settings, "LLM_TOTAL_TIMEOUT_SECONDS"),
        )

    def delay(self, attempt: int, error: BaseException, jitter: float) -> float:
        """Wait before attempt ``attempt + 1``: the provider's Retry-After (capped at
        ``max_delay``) or full-jitter exponential backoff; ``jitter`` is in [0, 1]."""
        asked = getattr(error, "retry_after", None)
        if isinstance(asked, (int, float)) and asked >= 0:
            return min(float(asked), self.max_delay)
        return min(self.max_delay, self.base_delay * 2 ** (attempt - 1)) * jitter


class LLMManager:
    def __init__(
        self,
        registry: LLMProviderRegistry,
        event_bus: EventBus | None = None,
        *,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus
        self._retry = retry or RetryPolicy()
        self._sleep = sleep
        self._jitter = jitter

    def providers(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self._registry.providers())

    def models(self) -> tuple[LLMModel, ...]:
        return tuple(model for provider in self._registry.providers() for model in provider.models())

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = monotonic()
        deadline = started + self._retry.total_timeout
        correlation = {key: value for key, value in request.metadata.items() if key in {"agent_id", "interaction_id"} and isinstance(value, str)}
        base = {"provider": request.model.provider, "model": request.model.model_name, **correlation}

        def elapsed_ms() -> int:
            return round((monotonic() - started) * 1000)

        try:
            provider = self._registry.resolve(request.model.provider)
        except Exception as error:
            await self._failed(base, error, attempts=0, elapsed_ms=elapsed_ms())
            raise
        base["provider"] = provider.name
        await self._publish(LLMRequested, base)

        attempt = 0
        while True:
            attempt += 1
            remaining = deadline - monotonic()
            try:
                if remaining <= 0:
                    raise LLMTimeoutError(f"{provider.name} did not respond within {self._retry.total_timeout:g} s.")
                # A hard bound per attempt, on top of the SDK's own request timeout.
                response = await asyncio.wait_for(provider.generate(request), timeout=remaining)
            except asyncio.CancelledError:
                await self._failed(base, None, attempts=attempt, elapsed_ms=elapsed_ms(), cancelled=True)
                raise
            except Exception as caught:
                error = _normalized(caught, provider.name, self._retry.total_timeout)
                wait = self._retry.delay(attempt, error, self._jitter()) if getattr(error, "retryable", False) else None
                if wait is not None and attempt < self._retry.max_attempts and monotonic() + wait < deadline:
                    await self._publish(LLMRetrying, {**base, "attempt": attempt, "error_category": error_category(error), "delay_ms": round(wait * 1000)})
                    logger.warning(
                        "Model request failed temporarily; retrying",
                        extra={"genesis_context": {"provider": provider.name, "model": request.model.model_name, "attempt": attempt, "error_category": error_category(error), "delay_ms": round(wait * 1000)}},
                    )
                    try:
                        await self._sleep(wait)
                    except asyncio.CancelledError:
                        await self._failed(base, None, attempts=attempt, elapsed_ms=elapsed_ms(), cancelled=True)
                        raise
                    continue
                exhausted = bool(getattr(error, "retryable", False)) and attempt > 1
                await self._failed(base, error, attempts=attempt, elapsed_ms=elapsed_ms(), exhausted=exhausted)
                if exhausted and isinstance(error, LLMRuntimeError):
                    raise _after_attempts(error, attempt) from caught
                if error is caught:
                    raise
                raise error from caught
            await self._publish(
                LLMCompleted,
                {
                    **base,
                    "model": response.model.model_name,
                    "duration_ms": elapsed_ms(),
                    "attempts": attempt,
                    "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "total_tokens": response.usage.total_tokens},
                },
            )
            return response

    async def _failed(
        self, base: dict[str, object], error: BaseException | None, *, attempts: int, elapsed_ms: int, exhausted: bool = False, cancelled: bool = False
    ) -> None:
        # Types and categories only: never messages, prompts or credentials.
        payload: dict[str, object] = {
            **base,
            "duration_ms": elapsed_ms,
            "attempts": attempts,
            "error_type": "CancelledError" if cancelled else type(error).__name__,
            "error_category": "cancelled" if cancelled else error_category(error) if error is not None else "provider_error",
            "retries_exhausted": exhausted,
        }
        try:
            await self._publish(LLMFailed, payload)
        except asyncio.CancelledError:
            pass  # recording must not mask the original outcome

    async def _publish(self, event_type, payload: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
        if self._event_bus is not None:
            await self._event_bus.publish(event_type(source="llm_manager", payload=dict(payload)))


def _normalized(error: Exception, provider: str, total_timeout: float) -> Exception:
    """The runtime's own error for a failure the adapter didn't classify (e.g. our deadline)."""
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)) and not isinstance(error, LLMRuntimeError):
        return LLMTimeoutError(f"{provider} did not respond within {total_timeout:g} s.")
    return error


def _after_attempts(error: LLMRuntimeError, attempts: int) -> LLMRuntimeError:
    """The same kind of error (so callers map it the same way), saying retries ran out."""
    try:
        exhausted = type(error)(f"{error} Gave up after {attempts} attempts.")
    except TypeError:
        return error
    exhausted.attempts = attempts  # type: ignore[attr-defined]
    return exhausted
