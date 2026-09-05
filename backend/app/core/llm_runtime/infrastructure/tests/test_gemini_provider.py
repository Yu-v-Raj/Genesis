"""Unit tests for the native Gemini provider adapter."""

from types import SimpleNamespace
from typing import Any

import pytest

from backend.app.core.core_services.config.settings import Settings
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.exceptions import LLMConfigurationError, LLMProviderError
from backend.app.core.llm_runtime.domain.models import (
    GenerationConfig,
    LLMModel,
    LLMRequest,
    Message,
    MessageRole,
)
from backend.app.core.llm_runtime.infrastructure.gemini_provider import GeminiProvider


class FakeModels:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **kwargs: object) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, models: FakeModels) -> None:
        self.aio = SimpleNamespace(models=models)


def gemini_request() -> LLMRequest:
    return LLMRequest(
        model=LLMModel(provider="gemini", model_name="gemini-3.6-flash"),
        messages=(
            Message(role=MessageRole.SYSTEM, content="Be concise."),
            Message(role=MessageRole.USER, content="Hello"),
            Message(role=MessageRole.ASSISTANT, content="Hi"),
            Message(role=MessageRole.TOOL, content="Tool result"),
        ),
        generation=GenerationConfig(temperature=0.2, max_tokens=64),
    )


def configured_settings() -> Settings:
    return Settings(GEMINI_API_KEY="gemini-test-key")


def unconfigured_settings() -> Settings:
    return Settings(GEMINI_API_KEY=None)


def test_model_metadata_reflects_configuration_and_registry_registration() -> None:
    configured = GeminiProvider(configured_settings(), client_factory=lambda *_: FakeClient(FakeModels()))
    unconfigured = GeminiProvider(unconfigured_settings())
    registry = LLMProviderRegistry()
    registry.register(configured)

    assert configured.models() == (
        LLMModel(
            provider="gemini",
            model_name="gemini-3.6-flash",
            capabilities=frozenset({"chat"}),
            metadata={"configured": True},
        ),
    )
    assert unconfigured.models()[0].metadata == {"configured": False}
    assert tuple(provider.name for provider in registry.providers()) == ("gemini",)


@pytest.mark.asyncio
async def test_missing_api_key_raises_configuration_error_only_when_generating() -> None:
    provider = GeminiProvider(unconfigured_settings())

    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY"):
        await provider.generate(gemini_request())


@pytest.mark.asyncio
async def test_lazy_client_configuration_error_is_not_translated_to_provider_error() -> None:
    def unavailable_client(*_: object) -> FakeClient:
        raise LLMConfigurationError("Gemini support requires the optional 'google-genai' package.")

    provider = GeminiProvider(configured_settings(), client_factory=unavailable_client)

    with pytest.raises(LLMConfigurationError, match="google-genai"):
        await provider.generate(gemini_request())


@pytest.mark.asyncio
async def test_generation_normalizes_response_usage_and_supported_settings() -> None:
    response = SimpleNamespace(
        text="Genesis is an agent operating system.",
        candidates=(SimpleNamespace(finish_reason=SimpleNamespace(value="STOP")),),
        usage_metadata=SimpleNamespace(
            prompt_token_count=11,
            candidates_token_count=7,
            total_token_count=18,
        ),
    )
    models = FakeModels(response=response)
    factory_calls: list[tuple[str, float]] = []
    provider = GeminiProvider(
        configured_settings(),
        client_factory=lambda api_key, timeout: (
            factory_calls.append((api_key, timeout)) or FakeClient(models)
        ),
    )

    result = await provider.generate(gemini_request())

    assert factory_calls == [("gemini-test-key", 30.0)]
    assert result.content == "Genesis is an agent operating system."
    assert result.finish_reason == "stop"
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.usage.total_tokens == 18
    assert result.tool_calls == ()
    assert models.calls == [
        {
            "model": "gemini-3.6-flash",
            "contents": [
                {"role": "user", "parts": [{"text": "Hello"}]},
                {"role": "model", "parts": [{"text": "Hi"}]},
                {"role": "user", "parts": [{"text": "Tool result"}]},
            ],
            "config": {
                "temperature": 0.2,
                "max_output_tokens": 64,
                "system_instruction": "Be concise.",
            },
        }
    ]


@pytest.mark.asyncio
async def test_provider_failure_and_event_payload_do_not_expose_credentials_or_prompts() -> None:
    secret = "gemini-test-key"
    provider = GeminiProvider(
        configured_settings(),
        client_factory=lambda *_: FakeClient(FakeModels(error=RuntimeError(secret))),
    )
    registry = LLMProviderRegistry()
    registry.register(provider)
    events = []
    event_bus = EventBus()
    event_bus.subscribe(events.append)
    request = LLMRequest(
        model=LLMModel(provider="gemini", model_name="gemini-3.6-flash"),
        messages=(Message(role=MessageRole.USER, content="secret prompt"),),
    )

    with pytest.raises(LLMProviderError, match="Gemini generation failed"):
        await LLMManager(registry, event_bus).generate(request)

    assert [event.event_type for event in events] == ["llm.requested", "llm.failed"]
    assert secret not in str(events[-1].payload)
    assert "secret prompt" not in str(events[-1].payload)
    diagnostic = provider._sanitized_error_message(
        RuntimeError(f"authorization: Bearer {secret}; secret prompt"), request
    )
    assert secret not in diagnostic
    assert "secret prompt" not in diagnostic
