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
