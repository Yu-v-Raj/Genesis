"""Stable LLM Runtime failure categories.

Every failure carries a provider-neutral ``category`` (recorded with executions and
``llm.*`` events) and says whether it is ``retryable``: only failures where repeating the
same model request can reasonably succeed are. Generating a reply has no side effects, so
repeating a request is safe; tools run outside the LLM Runtime and are never repeated by it.
"""


class LLMRuntimeError(Exception):
    """Base class for provider-agnostic LLM Runtime failures."""

    category = "provider_error"
    retryable = False


class ProviderNotFoundError(LLMRuntimeError):
    category = "configuration"


class ProviderUnavailableError(LLMRuntimeError):
    category = "configuration"


class LLMConfigurationError(ProviderUnavailableError):
    """Missing or rejected credentials, or a model the credential can't use."""


class LLMProviderError(LLMRuntimeError):
    """The provider failed in a way retrying the same request won't fix (e.g. invalid request)."""


class LLMTransientError(LLMProviderError):
    """A temporary provider failure: overloaded, unavailable, or the connection broke."""

    category = "provider_unavailable"
    retryable = True

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        # Seconds the provider asked us to wait, when it said (Retry-After).
        self.retry_after = retry_after


class LLMRateLimitError(LLMTransientError):
    """Rate limit or quota (HTTP 429)."""

    category = "rate_limited"


class LLMTimeoutError(LLMProviderError):
    category = "timeout"
    retryable = True


class LLMResponseNormalizationError(LLMProviderError):
    category = "invalid_response"


def error_category(error: BaseException) -> str:
    """The provider-neutral category for any failure of a model request."""
    if isinstance(error, LLMRuntimeError):
        return error.category
    if isinstance(error, TimeoutError):
        return "timeout"
    return "provider_error"
