"""Translate provider SDK failures into provider-neutral LLM Runtime errors.

SDK exception classes stay inside the adapters; this module only looks at the HTTP status
an SDK error carries and at whether it is a timeout, so both adapters classify the same
situations the same way:

- 401/403: the credential was rejected -> ``LLMConfigurationError`` (HTTP 503), with a
  message saying which setting to fix. Retrying cannot help.
- 404: the model is not available to this credential -> ``LLMConfigurationError``.
- 429: rate limit or quota -> ``LLMRateLimitError`` (HTTP 502), retryable, honouring the
  provider's Retry-After when it sends one.
- 408, 500, 502, 503, 504 and broken connections -> ``LLMTransientError`` (HTTP 502), retryable.
- any timeout type (asyncio, httpx, SDK-specific) -> ``LLMTimeoutError`` (HTTP 504), retryable.
- anything else (e.g. 400 invalid request) -> ``LLMProviderError`` (HTTP 502), not retried.
"""

import asyncio

from backend.app.core.llm_runtime.domain.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRuntimeError,
    LLMTimeoutError,
    LLMTransientError,
)

TRANSIENT_STATUSES = frozenset({408, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 3600.0


def http_status(error: BaseException) -> int | None:
    """Return the HTTP status an SDK error carries (``code`` or ``status_code``), if any."""
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
            return value
    return None


def is_timeout(error: BaseException) -> bool:
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return True
    # httpx.TimeoutException, openai.APITimeoutError, ... without importing the SDKs.
    return any("Timeout" in cls.__name__ for cls in type(error).__mro__)


def is_connection_failure(error: BaseException) -> bool:
    """openai.APIConnectionError, httpx.ConnectError/NetworkError/RemoteProtocolError, OSError."""
    if isinstance(error, (ConnectionError,)):
        return True
    names = {cls.__name__ for cls in type(error).__mro__}
    return bool(names & {"APIConnectionError", "ConnectError", "NetworkError", "RemoteProtocolError", "ReadError", "WriteError"})


def retry_after_seconds(error: BaseException) -> float | None:
    """The delay the provider asked for (``Retry-After`` seconds), bounded; None if absent."""
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get("retry-after-ms")
        if value is not None:
            seconds = float(value) / 1000
        else:
            value = headers.get("retry-after")
            if value is None:
                return None
            seconds = float(value)  # an HTTP date is ignored: the default backoff applies
    except (TypeError, ValueError, AttributeError):
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)


def classify_provider_failure(
    error: BaseException, *, provider: str, model: str, key_setting: str
) -> LLMRuntimeError:
    """Map an unexpected SDK failure to the error callers and the API understand."""
    if is_timeout(error):
        return LLMTimeoutError(f"{provider} did not respond in time.")
    status = http_status(error)
    if status in (401, 403):
        return LLMConfigurationError(
            f"{provider} rejected the configured API key (HTTP {status}). Check {key_setting} "
            "in the backend .env file, then restart the backend."
        )
    if status == 404:
        return LLMConfigurationError(f"{provider} model '{model}' is not available to the configured API key.")
    if status == 429:
        return LLMRateLimitError(f"{provider} rate limit or quota was exceeded. Try again later.", retry_after=retry_after_seconds(error))
    if status in TRANSIENT_STATUSES:
        return LLMTransientError(f"{provider} is temporarily unavailable (HTTP {status}).", retry_after=retry_after_seconds(error))
    if status is None and is_connection_failure(error):
        return LLMTransientError(f"Genesis could not reach {provider}.")
    if status is not None:
        return LLMProviderError(f"{provider} refused the request (HTTP {status}).")
    return LLMProviderError(f"{provider} generation failed.")
