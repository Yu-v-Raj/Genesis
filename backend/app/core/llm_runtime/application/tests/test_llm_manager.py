"""Deterministic coverage for provider-neutral LLM Runtime behavior."""

import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.exceptions import ProviderNotFoundError
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, Message, MessageRole, Usage


class FakeProvider(LLMProvider):
    @property
    def name(self) -> str: return "fake"
    def models(self) -> tuple[LLMModel, ...]: return (LLMModel(provider="fake", model_name="fake-1"),)
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="deterministic", model=request.model, finish_reason="stop", usage=Usage(input_tokens=3, output_tokens=1, total_tokens=4))


class FailingProvider(FakeProvider):
    @property
    def name(self) -> str: return "failing"
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("provider unavailable")


def request() -> LLMRequest:
    return LLMRequest(model=LLMModel(provider="fake", model_name="fake-1"), messages=(Message(role=MessageRole.USER, content="Hello"),))


def test_domain_records_are_immutable_and_validate_usage() -> None:
    message = Message(role=MessageRole.SYSTEM, content="Be concise.", metadata={"scope": "test"})
    assert message.metadata["scope"] == "test"
    with pytest.raises(ValueError, match="cannot be negative"):
        Usage(input_tokens=-1)


@pytest.mark.asyncio
async def test_registry_resolution_runtime_delegation_usage_and_events() -> None:
    registry = LLMProviderRegistry(); registry.register(FakeProvider())
    events = []; event_bus = EventBus(); event_bus.subscribe(events.append)
    response = await LLMManager(registry, event_bus).generate(request())
    assert response.content == "deterministic"
    assert response.usage.total_tokens == 4
    assert [event.event_type for event in events] == ["llm.requested", "llm.completed"]
    assert "Hello" not in str(events[0].payload)


def test_unknown_provider_is_clear() -> None:
    with pytest.raises(ProviderNotFoundError):
        LLMProviderRegistry().resolve("missing")


@pytest.mark.asyncio
async def test_provider_failure_emits_sanitized_event() -> None:
    registry = LLMProviderRegistry(); registry.register(FailingProvider())
    events = []; event_bus = EventBus(); event_bus.subscribe(events.append)
    failed_request = LLMRequest(model=LLMModel(provider="failing", model_name="fake-1"), messages=(Message(role=MessageRole.USER, content="secret prompt"),))
    with pytest.raises(RuntimeError):
        await LLMManager(registry, event_bus).generate(failed_request)
    assert [event.event_type for event in events] == ["llm.requested", "llm.failed"]
    assert "secret prompt" not in str(events[-1].payload)
