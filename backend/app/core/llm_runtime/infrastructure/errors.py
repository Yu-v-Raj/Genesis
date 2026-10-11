"""Translate provider SDK failures into provider-neutral LLM Runtime errors.

SDK exception classes stay inside the adapters; this module only looks at the HTTP status
an SDK error carries and at whether it is a timeout, so both adapters classify the same
situations the same way:

- 401/403: the credential was rejected -> ``LLMConfigurationError`` (HTTP 503), with a
  message saying which setting to fix. Retrying cannot help.
- 404: the model is not available to this credential -> ``LLMConfigurationError``.
- 429: rate limit or quota -> ``LLMProviderError`` (HTTP 502), worth retrying later.
- any timeout type (asyncio, httpx, SDK-specific) -> ``LLMTimeoutError`` (HTTP 504).
"""

import asyncio

from backend.app.core.llm_runtime.domain.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRuntimeError,
    LLMTimeoutError,
)


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
        return LLMProviderError(f"{provider} rate limit or quota was exceeded. Try again later.")
    return LLMProviderError(f"{provider} generation failed.")
