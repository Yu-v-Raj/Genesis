"""Focused single-turn Agent to provider-neutral LLM Runtime coverage."""

import asyncio

import pytest

from backend.app.core.agent_runtime.application.agent_interaction_service import (
    AgentInteractionService,
)
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.agent_runtime.domain.exceptions import AgentLifecycleError
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.exceptions import LLMProviderError
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, Usage
from backend.app.core.observability.domain.events import Event


class RecordingProvider(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider=self.name, model_name="fake-1"),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content="deterministic response",
            model=request.model,
            finish_reason="stop",
            usage=Usage(input_tokens=3, output_tokens=2, total_tokens=5),
        )


class FailingProvider(RecordingProvider):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise LLMProviderError("provider failed")


class BlockingProvider(RecordingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        self.started.set()
        await self.release.wait()
        return LLMResponse(content="done", model=request.model)


def service_with_provider(
    provider: LLMProvider,
) -> tuple[AgentManager, AgentInteractionService, list[Event]]:
    event_bus = EventBus()
    events: list[Event] = []
    event_bus.subscribe(events.append)
    agent_registry = AgentRegistry(event_bus)
    agent_manager = AgentManager(agent_registry, event_bus)
    provider_registry = LLMProviderRegistry()
    provider_registry.register(provider)
    service = AgentInteractionService(
        agent_registry,
        agent_manager,
        LLMManager(provider_registry, event_bus),
    )
    return agent_manager, service, events


@pytest.mark.asyncio
async def test_agent_chat_returns_to_idle_and_retains_ephemeral_session_messages() -> None:
    provider = RecordingProvider()
    manager, service, events = service_with_provider(provider)
    agent = await manager.create_agent(
        name="assistant",
        description="Answers questions.",
        type="chat",
        llm_model=LLMModel(provider="fake", model_name="fake-1"),
    )
    await manager.initialize_agent(agent.id)

    completed, response = await service.chat(agent.id, "What is Genesis?")

    assert completed.status is AgentStatus.IDLE
    assert response.content == "deterministic response"
    assert provider.requests[0].messages[0].content == "What is Genesis?"
    assert provider.requests[0].messages[0].role.value == "user"
    assert [event.event_type for event in events][-5:] == [
        "agent.status_changed",
        "agent.started",
        "llm.requested",
        "llm.completed",
        "agent.status_changed",
    ]
    session = await manager.get_session(agent.id)
    assert [message.content for message in session.messages] == [
        "What is Genesis?",
        "deterministic response",
    ]


@pytest.mark.asyncio
async def test_agent_chat_failure_returns_the_agent_to_idle() -> None:
    manager, service, events = service_with_provider(FailingProvider())
    agent = await manager.create_agent(
        name="assistant",
        description="Answers questions.",
        type="chat",
        llm_model=LLMModel(provider="fake", model_name="fake-1"),
    )
    await manager.initialize_agent(agent.id)

    with pytest.raises(LLMProviderError, match="provider failed"):
        await service.chat(agent.id, "Hello")

    assert (await manager.get_context(agent.id)).current_state is AgentStatus.IDLE
    assert [event.event_type for event in events][-5:] == [
        "agent.status_changed",
        "agent.started",
        "llm.requested",
        "llm.failed",
        "agent.status_changed",
    ]


@pytest.mark.asyncio
async def test_same_agent_supports_multiple_sequential_chats() -> None:
    provider = RecordingProvider()
    manager, service, _ = service_with_provider(provider)
    agent = await manager.create_agent(
        name="assistant",
        description="Answers questions.",
        type="chat",
        llm_model=LLMModel(provider="fake", model_name="fake-1"),
    )
    await manager.initialize_agent(agent.id)

    first, _ = await service.chat(agent.id, "First question")
    second, _ = await service.chat(agent.id, "Second question")

    assert first.status is AgentStatus.IDLE
    assert second.status is AgentStatus.IDLE
    assert [message.content for message in provider.requests[1].messages] == [
        "First question",
        "deterministic response",
        "Second question",
    ]


@pytest.mark.asyncio
async def test_chat_rejects_a_second_interaction_while_agent_is_running() -> None:
    provider = BlockingProvider()
    manager, service, _ = service_with_provider(provider)
    agent = await manager.create_agent(
        name="assistant",
        description="Answers questions.",
        type="chat",
        llm_model=LLMModel(provider="fake", model_name="fake-1"),
    )
    await manager.initialize_agent(agent.id)

    first_chat = asyncio.create_task(service.chat(agent.id, "First"))
    await provider.started.wait()
    with pytest.raises(AgentLifecycleError):
        await service.chat(agent.id, "Second")
    provider.release.set()
    completed, _ = await first_chat

    assert completed.status is AgentStatus.IDLE
