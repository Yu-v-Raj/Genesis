"""Restart behaviour: a new runtime built on the same database restores Agents and sessions."""

import asyncio
from collections.abc import Sequence

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.agent_runtime.application.agent_configuration_service import (
    AgentConfigurationService,
)
from backend.app.core.agent_runtime.application.agent_interaction_service import (
    AgentInteractionService,
)
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.exceptions import SessionNotFoundError
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.agent_runtime.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyAgentRepository,
    SqlAlchemySessionRepository,
)
from backend.app.core.core_services.event_bus import EventBus
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
from backend.app.core.observability.domain.events import Event
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import builtin_tools


MODEL = LLMModel(provider="fake", model_name="fake-1")


class ScriptedProvider(LLMProvider):
    def __init__(self, *responses: LLMResponse | Exception) -> None:
        self._responses = list(responses)
        self.requests: list[LLMRequest] = []
        self.started = asyncio.Event()
        self.block = False

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (MODEL,)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class Runtime:
    """One backend "process": fresh services over a shared database."""

    def __init__(self, factory: async_sessionmaker[AsyncSession], provider: ScriptedProvider) -> None:
        self.events: list[Event] = []
        bus = EventBus()
        bus.subscribe(self.events.append)
        self.registry = AgentRegistry(bus, SqlAlchemyAgentRepository(factory))
        self.manager = AgentManager(self.registry, bus, SqlAlchemySessionRepository(factory))
        tool_registry = ToolRegistry(bus)
        self.tools = ToolRuntimeManager(tool_registry, ToolExecutor(tool_registry, bus), bus)
        providers = LLMProviderRegistry()
        providers.register(provider)
        llm = LLMManager(providers, bus)
        self.configuration = AgentConfigurationService(self.registry, self.manager, llm, self.tools)
        self.interaction = AgentInteractionService(self.registry, self.manager, llm, tool_manager=self.tools)
        self.provider = provider

    async def start(self) -> "Runtime":
        for tool in builtin_tools():
            await self.tools.register(tool)
        await self.manager.restore_agents()
        return self


async def runtime(factory: async_sessionmaker[AsyncSession], *responses: LLMResponse | Exception) -> Runtime:
    return await Runtime(factory, ScriptedProvider(*responses)).start()


def tool_turn() -> Sequence[LLMResponse]:
    return (
        LLMResponse(
            content=None,
            model=MODEL,
            tool_calls=(
                ToolCall(
                    call_id="c1",
                    name="calculator",
                    arguments={"expression": "25 * 4"},
                    metadata={"thought_signature": b"sig"},
                ),
            ),
        ),
        LLMResponse(content="It is 100.", model=MODEL),
    )


@pytest.mark.asyncio
async def test_agent_configuration_and_history_survive_a_restart(session_factory) -> None:
    first = await runtime(session_factory, *tool_turn())
    created = await first.configuration.create_agent(
        name="Math helper",
        description="Arithmetic.",
        type="assistant",
        llm_model=MODEL,
        allowed_tools=("calculator",),
        instructions="Use the calculator.",
        initialize=True,
    )
    await first.configuration.update_configuration(created.id, allowed_tools=("calculator", "echo"))
    _, _, summary = await first.interaction.chat_with_summary(created.id, "Calculate 25 * 4")

    second = await runtime(session_factory, LLMResponse(content="Still 100.", model=MODEL))
    restored = second.registry.get(created.id)

    assert restored.status is AgentStatus.IDLE
    assert (restored.llm_model, restored.allowed_tools, restored.instructions) == (
        MODEL,
        ("calculator", "echo"),
        "Use the calculator.",
    )
    assert [e.event_type for e in second.events if e.event_type.startswith("agent.")][-1] == "agent.restored"
    session = await second.manager.get_session(created.id)
    assert session.id == summary.session_id
    assert len(session.messages) == 4

    await second.interaction.chat(created.id, "And again?")
    replayed = second.provider.requests[0].messages
    assert [m.role for m in replayed] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
        MessageRole.ASSISTANT,
        MessageRole.TOOL,
        MessageRole.ASSISTANT,
        MessageRole.USER,
    ]
    assert replayed[2].metadata["tool_calls"][0].metadata["thought_signature"] == b"sig"


@pytest.mark.asyncio
async def test_lifecycle_restoration_policy(session_factory) -> None:
    first = await runtime(session_factory)
    created = await first.configuration.create_agent(name="a", description="d", type="t")
    stopped = await first.configuration.create_agent(name="b", description="d", type="t", initialize=True)
    await first.manager.stop_agent(stopped.id)

    second = await runtime(session_factory)

    assert second.registry.get(created.id).status is AgentStatus.CREATED
    assert second.registry.get(stopped.id).status is AgentStatus.STOPPED


@pytest.mark.asyncio
async def test_crash_mid_turn_restores_idle_without_partial_history(session_factory) -> None:
    first = await runtime(session_factory, LLMResponse(content="never delivered", model=MODEL))
    agent = await first.configuration.create_agent(
        name="a", description="d", type="t", llm_model=MODEL, initialize=True
    )
    first.provider.block = True
    in_flight = asyncio.create_task(first.interaction.chat(agent.id, "Hello"))
    await first.provider.started.wait()
    assert first.registry.get(agent.id).status is AgentStatus.RUNNING

    second = await runtime(session_factory)  # the first process "crashed" here
    in_flight.cancel()

    assert second.registry.get(agent.id).status is AgentStatus.IDLE
    assert (await second.manager.get_session(agent.id)).messages == ()


@pytest.mark.asyncio
async def test_failed_reinitialization_keeps_the_definition(session_factory, monkeypatch) -> None:
    first = await runtime(session_factory)
    agent = await first.configuration.create_agent(
        name="a", description="d", type="t", llm_model=MODEL, initialize=True
    )

    second = Runtime(session_factory, ScriptedProvider())

    async def broken_initialize(_agent_id):
        raise RuntimeError("initialization failed")

    monkeypatch.setattr(second.manager, "initialize_agent", broken_initialize)
    await second.start()

    restored = second.registry.get(agent.id)
    assert restored.status is AgentStatus.CREATED
    assert restored.llm_model == MODEL

    del second.manager.initialize_agent  # the fault clears; recovery uses the normal lifecycle
    recovered = await second.manager.initialize_agent(agent.id)
    assert recovered.status is AgentStatus.IDLE


@pytest.mark.asyncio
async def test_new_sessions_are_distinct_and_old_ones_can_be_resumed(session_factory) -> None:
    rt = await runtime(
        session_factory,
        LLMResponse(content="first answer", model=MODEL),
        LLMResponse(content="fresh answer", model=MODEL),
        LLMResponse(content="resumed answer", model=MODEL),
    )
    agent = await rt.configuration.create_agent(name="a", description="d", type="t", llm_model=MODEL, initialize=True)
    other = await rt.configuration.create_agent(name="b", description="d", type="t", llm_model=MODEL, initialize=True)
    first_session = await rt.manager.get_session(agent.id)
    await rt.interaction.chat(agent.id, "First conversation")

    fresh = await rt.manager.start_session(agent.id)
    await rt.interaction.chat(agent.id, "Second conversation")
    assert [m.content for m in rt.provider.requests[1].messages] == ["Second conversation"]

    await rt.interaction.chat(agent.id, "Back to the first", first_session.id)
    assert [m.content for m in rt.provider.requests[2].messages] == [
        "First conversation",
        "first answer",
        "Back to the first",
    ]
    summaries = await rt.manager.list_sessions(agent.id)
    assert [s.id for s in summaries] == [first_session.id, fresh.id]
    with pytest.raises(SessionNotFoundError):
        await rt.manager.get_session(other.id, first_session.id)


@pytest.mark.asyncio
async def test_failed_turn_is_not_stored(session_factory) -> None:
    rt = await runtime(session_factory, LLMProviderError("down"), *tool_turn())
    agent = await rt.configuration.create_agent(name="a", description="d", type="t", llm_model=MODEL, initialize=True)

    with pytest.raises(LLMProviderError):
        await rt.interaction.chat(agent.id, "Calculate 25 * 4")
    assert (await rt.manager.get_session(agent.id)).messages == ()

    await rt.interaction.chat(agent.id, "Calculate 25 * 4")
    restarted = await runtime(session_factory)
    assert len((await restarted.manager.get_session(agent.id)).messages) == 4
