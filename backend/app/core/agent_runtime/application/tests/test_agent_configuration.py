"""v0.10E-B coverage: validated Agent configuration, instructions, and session integrity."""

import asyncio
import json

import pytest

from backend.app.core.agent_runtime.application.agent_configuration_service import (
    AgentConfigurationService,
)
from backend.app.core.agent_runtime.application.agent_interaction_service import (
    AgentInteractionService,
)
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.exceptions import (
    AgentConfigurationError,
    AgentUnavailableError,
)
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.config.settings import Settings
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.exceptions import LLMProviderError
from backend.app.core.llm_runtime.domain.models import (
    LLMModel,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ToolCall,
)
from backend.app.core.llm_runtime.infrastructure.openai_provider import OpenAIProvider
from backend.app.core.observability.domain.events import Event
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import builtin_tools


MODEL = LLMModel(provider="fake", model_name="fake-1")


class ScriptedProvider(LLMProvider):
    """Return queued responses; an exception in the queue is raised instead."""

    def __init__(self, *responses: LLMResponse | Exception) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []
        self.started = asyncio.Event()
        self.release: asyncio.Event | None = None

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (MODEL,)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        self.started.set()
        if self.release is not None:
            await self.release.wait()
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Harness:
    def __init__(self, provider: ScriptedProvider) -> None:
        self.events: list[Event] = []
        self.event_bus = EventBus()
        self.event_bus.subscribe(self.events.append)
        self.registry = AgentRegistry(self.event_bus)
        self.manager = AgentManager(self.registry, self.event_bus)
        tool_registry = ToolRegistry(self.event_bus)
        self.tools = ToolRuntimeManager(tool_registry, ToolExecutor(tool_registry, self.event_bus), self.event_bus)
        providers = LLMProviderRegistry()
        providers.register(provider)
        self.llm = LLMManager(providers, self.event_bus)
        self.configuration = AgentConfigurationService(self.registry, self.manager, self.llm, self.tools)
        self.interaction = AgentInteractionService(self.registry, self.manager, self.llm, tool_manager=self.tools)
        self.provider = provider

    async def register_tools(self) -> "Harness":
        for tool in builtin_tools():
            await self.tools.register(tool)
        return self

    async def ready_agent(self, **configuration: object):
        return await self.configuration.create_agent(
            name="assistant",
            description="Answers questions.",
            type="chat",
            llm_model=MODEL,
            initialize=True,
            **configuration,
        )


async def harness(*responses: LLMResponse | Exception) -> Harness:
    return await Harness(ScriptedProvider(*responses)).register_tools()


@pytest.mark.asyncio
async def test_create_rejects_unknown_provider_model_and_tools() -> None:
    h = await harness()
    cases = [
        ({"llm_model": LLMModel(provider="nope", model_name="x")}, "llm_model", "Unknown LLM provider 'nope'"),
        ({"llm_model": LLMModel(provider="fake", model_name="other")}, "llm_model", "Model 'other' is not available"),
        ({"allowed_tools": ("calculator", "rm_rf")}, "allowed_tools", "Unknown tools: rm_rf"),
        ({"instructions": "x" * 4001}, "instructions", "at most 4000"),
    ]
    for configuration, field, message in cases:
        with pytest.raises(AgentConfigurationError) as caught:
            await h.configuration.create_agent(name="a", description="d", type="t", **configuration)
        assert caught.value.field == field
        assert message in str(caught.value)
    assert h.registry.count() == 0


@pytest.mark.asyncio
async def test_create_can_initialize_and_deduplicates_tools() -> None:
    h = await harness()

    agent = await h.ready_agent(allowed_tools=("calculator", "echo", "calculator"), instructions="Be brief.")

    assert agent.status is AgentStatus.IDLE
    assert agent.allowed_tools == ("calculator", "echo")
    assert agent.instructions == "Be brief."


@pytest.mark.asyncio
async def test_unconfigured_provider_is_accepted_and_reported_by_its_model() -> None:
    """Missing credentials do not block setup; the model listing says the provider is unusable."""
    providers = LLMProviderRegistry()
    providers.register(OpenAIProvider(Settings(OPENAI_API_KEY=None, _env_file=None)))
    llm = LLMManager(providers)
    event_bus = EventBus()
    registry = AgentRegistry(event_bus)
    tool_registry = ToolRegistry(event_bus)
    service = AgentConfigurationService(
        registry,
        AgentManager(registry, event_bus),
        llm,
        ToolRuntimeManager(tool_registry, ToolExecutor(tool_registry, event_bus), event_bus),
    )
    openai_model = llm.models()[0]

    agent = await service.create_agent(
        name="a", description="d", type="t", llm_model=LLMModel(provider="openai", model_name=openai_model.model_name)
    )

    assert agent.llm_model is not None
    assert openai_model.metadata["configured"] is False


@pytest.mark.asyncio
async def test_partial_configuration_update_keeps_other_fields_and_emits_safe_event() -> None:
    h = await harness()
    agent = await h.ready_agent(allowed_tools=("calculator",), instructions="Secret persona text")

    updated = await h.configuration.update_configuration(agent.id, allowed_tools=("echo",))

    assert updated.allowed_tools == ("echo",)
    assert updated.instructions == "Secret persona text"
    assert updated.llm_model == MODEL
    event = next(e for e in h.events if e.event_type == "agent.configuration_updated")
    assert event.payload == {"agent_id": str(agent.id), "changed": ["allowed_tools"]}
    assert "Secret persona text" not in json.dumps(dict(event.payload))

    removed = await h.configuration.update_configuration(agent.id, llm_model=None)
    assert removed.llm_model is None


@pytest.mark.asyncio
async def test_configuration_cannot_change_while_working_or_stopped() -> None:
    h = await harness(LLMResponse(content="done", model=MODEL))
    h.provider.release = asyncio.Event()
    agent = await h.ready_agent()

    chat = asyncio.create_task(h.interaction.chat(agent.id, "Hello"))
    await h.provider.started.wait()
    with pytest.raises(AgentUnavailableError):
        await h.configuration.update_configuration(agent.id, instructions="new")
    h.provider.release.set()
    await chat

    await h.manager.stop_agent(agent.id)
    with pytest.raises(AgentUnavailableError):
        await h.configuration.update_configuration(agent.id, instructions="new")


@pytest.mark.asyncio
async def test_instructions_are_sent_as_system_message_but_not_stored() -> None:
    h = await harness(LLMResponse(content="Hi!", model=MODEL), LLMResponse(content="Again", model=MODEL))
    agent = await h.ready_agent(instructions="  You are a terse assistant.  ")

    await h.interaction.chat(agent.id, "Hello")
    await h.interaction.chat(agent.id, "Hello again")

    first, second = h.provider.requests
    assert [(m.role, m.content) for m in first.messages] == [
        (MessageRole.SYSTEM, "You are a terse assistant."),
        (MessageRole.USER, "Hello"),
    ]
    assert [m.role for m in second.messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    session = await h.manager.get_session(agent.id)
    assert MessageRole.SYSTEM not in {message.role for message in session.messages}


@pytest.mark.asyncio
async def test_failed_turn_leaves_session_unchanged() -> None:
    """Regression: failed requests used to leave orphan user messages in the session."""
    h = await harness(
        LLMProviderError("provider down"),
        LLMResponse(
            content=None,
            model=MODEL,
            tool_calls=(ToolCall(call_id="c1", name="calculator", arguments={"expression": "1+1"}),),
        ),
        LLMProviderError("continuation failed"),
        LLMResponse(content="recovered", model=MODEL),
    )
    agent = await h.ready_agent()

    for _ in range(2):
        with pytest.raises(LLMProviderError):
            await h.interaction.chat(agent.id, "Calculate 1+1")
        assert (await h.manager.get_session(agent.id)).messages == ()
        assert h.registry.get(agent.id).status is AgentStatus.IDLE

    await h.interaction.chat(agent.id, "Hello")
    assert [m.content for m in h.provider.requests[-1].messages] == ["Hello"]


@pytest.mark.asyncio
async def test_session_messages_record_interaction_and_tool_outcome() -> None:
    h = await harness(
        LLMResponse(
            content=None,
            model=MODEL,
            tool_calls=(
                ToolCall(call_id="ok", name="calculator", arguments={"expression": "25*4"}),
                ToolCall(call_id="no", name="echo", arguments={"message": "x"}),
            ),
        ),
        LLMResponse(content="100", model=MODEL),
    )
    agent = await h.ready_agent(allowed_tools=("calculator",))

    _, _, summary = await h.interaction.chat_with_summary(agent.id, "Calculate")

    messages = (await h.manager.get_session(agent.id)).messages
    assert {m.metadata["interaction_id"] for m in messages} == {str(summary.interaction_id)}
    tool_messages = [m for m in messages if m.role is MessageRole.TOOL]
    assert [(m.metadata["tool_name"], m.metadata["tool_status"]) for m in tool_messages] == [
        ("calculator", "completed"),
        ("echo", "rejected"),
    ]
    assert [task.tool_name for task in h.tools.history()] == ["calculator"]


@pytest.mark.asyncio
async def test_stopping_during_an_interaction_is_not_undone() -> None:
    h = await harness(LLMResponse(content="late", model=MODEL))
    h.provider.release = asyncio.Event()
    agent = await h.ready_agent()

    chat = asyncio.create_task(h.interaction.chat(agent.id, "Hello"))
    await h.provider.started.wait()
    await h.manager.stop_agent(agent.id)
    h.provider.release.set()
    finished, _ = await chat

    assert finished.status is AgentStatus.STOPPED
    assert h.registry.get(agent.id).status is AgentStatus.STOPPED


@pytest.mark.asyncio
async def test_unavailable_agents_get_user_facing_reasons() -> None:
    h = await harness()
    created = await h.configuration.create_agent(name="a", description="d", type="t", llm_model=MODEL)
    with pytest.raises(AgentUnavailableError, match="isn't ready yet"):
        await h.interaction.chat(created.id, "Hello")

    await h.manager.stop_agent(created.id)
    with pytest.raises(AgentUnavailableError, match="stopped"):
        await h.interaction.chat(created.id, "Hello")
