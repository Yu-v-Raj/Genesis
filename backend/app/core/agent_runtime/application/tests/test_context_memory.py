"""Memories and trimmed history in the context sent to the model."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.core.agent_runtime.application.agent_interaction_service import AgentInteractionService
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.context_assembler import MEMORY_PREAMBLE, AgentContextAssembler
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, Message, MessageRole, ToolCall
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.memory.domain.memory_kind import MemoryKind
from backend.app.core.memory.domain.memory_record import MemoryRecord
from backend.app.core.memory.infrastructure.in_memory_provider import InMemoryProvider


MODEL = LLMModel(provider="fake", model_name="fake-1")


class Recorder(LLMProvider):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (MODEL,)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content="ok", model=request.model)


async def setup(**assembler: int):
    bus = EventBus()
    registry = AgentRegistry(bus)
    agents = AgentManager(registry, bus)
    memory = MemoryManager(InMemoryProvider(), bus)
    provider = Recorder()
    providers = LLMProviderRegistry(); providers.register(provider)
    service = AgentInteractionService(
        registry, agents, LLMManager(providers, bus), context_assembler=AgentContextAssembler(**assembler), memory=memory
    )
    agent = await agents.create_agent(name="a", description="d", type="t", llm_model=MODEL, instructions="Be brief.")
    await agents.initialize_agent(agent.id)
    return agents, memory, service, provider, agent


@pytest.mark.asyncio
async def test_the_agents_memories_reach_the_model_but_are_not_stored() -> None:
    agents, memory, service, provider, agent = await setup()
    await memory.create_memory(agent_id=agent.id, content="The user's name is Yuvraj.", kind=MemoryKind.FACT)
    await memory.create_memory(agent_id=agent.id, content="Prefers metric units.", kind=MemoryKind.PREFERENCE)
    await memory.create_memory(agent_id=uuid4(), content="Another Agent's secret.", kind=MemoryKind.FACT)

    await service.chat(agent.id, "What's my name?")

    system = [m.content for m in provider.requests[0].messages if m.role is MessageRole.SYSTEM]
    assert system[0] == "Be brief."
    assert system[1].startswith(MEMORY_PREAMBLE)
    assert system[1].index("Prefers metric units.") < system[1].index("Yuvraj")  # newest first
    assert "(fact) The user's name is Yuvraj." in system[1]
    assert "Another Agent's secret." not in "\n".join(system)
    stored = (await agents.get_session(agent.id)).messages
    assert MessageRole.SYSTEM not in {m.role for m in stored}


@pytest.mark.asyncio
async def test_no_memory_message_when_the_agent_has_none() -> None:
    _, _, service, provider, agent = await setup()
    await service.chat(agent.id, "Hello")
    assert [m.content for m in provider.requests[0].messages if m.role is MessageRole.SYSTEM] == ["Be brief."]


def test_memory_budget_keeps_the_newest_and_says_what_was_left_out() -> None:
    agent = Agent(name="a", description="d", type="t")
    start = datetime.now(UTC)
    memories = [
        MemoryRecord(agent_id=agent.id, content=f"memory {i}", created_at=start + timedelta(seconds=i))
        for i in range(25)
    ]
    block = AgentContextAssembler(max_memories=20).system_messages(agent, memories)[0].content
    assert "memory 24" in block and "memory 5" in block and "memory 4" not in block
    assert block.endswith("(5 older memories not shown.)")

    tight = AgentContextAssembler(max_memory_characters=40).system_messages(agent, memories)[0].content
    assert tight.count("- (note)") == 2


def test_history_keeps_whole_recent_turns_and_tool_pairs_together() -> None:
    def turn(i: int, with_tool: bool) -> list[Message]:
        tag = {"interaction_id": f"i{i}"}
        messages = [Message(role=MessageRole.USER, content=f"q{i}", metadata=tag)]
        if with_tool:
            messages += [
                Message(role=MessageRole.ASSISTANT, content="", metadata={**tag, "tool_calls": (ToolCall(call_id=f"c{i}", name="calculator"),)}),
                Message(role=MessageRole.TOOL, content="{}", metadata={**tag, "tool_call_id": f"c{i}", "tool_name": "calculator"}),
            ]
        return messages + [Message(role=MessageRole.ASSISTANT, content=f"a{i}", metadata=tag)]

    session = [*turn(1, True), *turn(2, False), *turn(3, True)]
    kept = AgentContextAssembler(max_history_turns=2).history(session)

    assert [m.content for m in kept][0] == "q2"
    assert [m.role for m in kept] == [
        MessageRole.USER, MessageRole.ASSISTANT,
        MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL, MessageRole.ASSISTANT,
    ]
    legacy = [Message(role=MessageRole.USER, content="x"), Message(role=MessageRole.ASSISTANT, content="y"), Message(role=MessageRole.USER, content="z")]
    assert [m.content for m in AgentContextAssembler(max_history_turns=1).history(legacy)] == ["z"]


@pytest.mark.asyncio
async def test_long_conversations_send_only_recent_turns() -> None:
    agents, _, service, provider, agent = await setup(max_history_turns=2)
    for i in range(4):
        await service.chat(agent.id, f"message {i}")

    sent = [m.content for m in provider.requests[-1].messages if m.role is not MessageRole.SYSTEM]
    assert sent == ["message 1", "ok", "message 2", "ok", "message 3"]
    assert len((await agents.get_session(agent.id)).messages) == 8  # nothing deleted from storage
