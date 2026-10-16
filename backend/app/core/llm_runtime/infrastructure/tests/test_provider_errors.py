"""Provider-neutral classification of SDK failures (shared by both adapters)."""

import asyncio

import httpx

from backend.app.core.llm_runtime.domain.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMTimeoutError,
)
from backend.app.core.llm_runtime.infrastructure.errors import classify_provider_failure, http_status


class OpenAIStyleError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__("openai-style")
        self.status_code = status_code


def classify(error: BaseException):
    return classify_provider_failure(error, provider="OpenAI", model="m", key_setting="OPENAI_API_KEY")


def test_status_codes_from_either_sdk_shape() -> None:
    assert http_status(OpenAIStyleError(401)) == 401
    assert http_status(Exception()) is None
    assert isinstance(classify(OpenAIStyleError(401)), LLMConfigurationError)
    assert "OPENAI_API_KEY" in str(classify(OpenAIStyleError(403)))
    assert isinstance(classify(OpenAIStyleError(429)), LLMProviderError)
    assert not isinstance(classify(OpenAIStyleError(429)), LLMConfigurationError)


def test_every_timeout_flavour_is_a_timeout() -> None:
    for error in (asyncio.TimeoutError(), TimeoutError(), httpx.ReadTimeout("slow"), httpx.ConnectTimeout("slow")):
        assert isinstance(classify(error), LLMTimeoutError), type(error)
    assert not isinstance(classify(httpx.ConnectError("refused")), LLMTimeoutError)


class WithHeaders(OpenAIStyleError):
    def __init__(self, status_code: int, headers: dict[str, str]) -> None:
        super().__init__(status_code)
        self.response = httpx.Response(status_code, headers=headers)


def test_transient_and_permanent_failures_are_distinct() -> None:
    from backend.app.core.llm_runtime.domain.exceptions import LLMRateLimitError, LLMTransientError

    for status in (408, 500, 502, 503, 504):
        error = classify(OpenAIStyleError(status))
        assert isinstance(error, LLMTransientError) and error.retryable and error.category == "provider_unavailable", status
    limited = classify(OpenAIStyleError(429))
    assert isinstance(limited, LLMRateLimitError) and limited.retryable and limited.category == "rate_limited"
    for status in (400, 401, 403, 404, 409, 422):
        error = classify(OpenAIStyleError(status))
        assert not error.retryable, status
    assert classify(OpenAIStyleError(400)).category == "provider_error"
    assert classify(OpenAIStyleError(401)).category == "configuration"
    assert classify(httpx.ConnectError("refused")).retryable
    assert classify(ConnectionResetError()).retryable
    assert classify(httpx.ReadTimeout("slow")).retryable and classify(httpx.ReadTimeout("slow")).category == "timeout"
    assert not classify(RuntimeError("unexpected")).retryable  # unknown failures are not retried


def test_retry_after_is_read_and_bounded() -> None:
    assert classify(WithHeaders(429, {"retry-after": "7"})).retry_after == 7.0
    assert classify(WithHeaders(503, {"retry-after-ms": "250"})).retry_after == 0.25
    assert classify(WithHeaders(429, {"retry-after": "999999"})).retry_after == 3600.0
    assert classify(WithHeaders(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})).retry_after is None
    assert classify(OpenAIStyleError(429)).retry_after is None
