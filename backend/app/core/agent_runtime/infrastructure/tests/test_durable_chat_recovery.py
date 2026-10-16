"""Failure injection for chat turns run as durable executions."""

import asyncio
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.app.core.approval_gateway.domain.approval import ApprovalResolution, ApprovalState, OperationBinding
from backend.app.core.agent_runtime.application.agent_interaction_service import AgentInteractionService
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.chat_work import CHAT_KIND, ChatWorkHandler, chat_metadata
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.agent_runtime.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyAgentRepository,
    SqlAlchemySessionRepository,
)
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.execution_runtime.application.execution_executor import ExecutionExecutor
from backend.app.core.execution_runtime.application.execution_manager import ExecutionManager
from backend.app.core.execution_runtime.domain.exceptions import ExecutionAbortedError, ExecutionRetryError
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus as S
from backend.app.core.execution_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyExecutionRepository
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, MessageRole, ToolCall
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_metadata import ToolMetadata
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus


class ApprovedForThisTest:
    """Stands in for a recorded operator approval so the crash-recovery path of a
    side-effecting tool can still be exercised. Confined to this test module: production
    uses the durable Approval Gateway, where nothing is approved without an operator."""

    async def resolve(self, binding: OperationBinding, *, reason: str) -> ApprovalResolution:
        return ApprovalResolution(approval_id=uuid5(NAMESPACE_URL, binding.digest), state=ApprovalState.APPROVED, operation_digest=binding.digest)

    async def consume(self, approval_id, operation_digest) -> bool:
        return True

    async def record_outcome(self, approval_id, **_: object) -> None:
        return None

    async def state_of(self, approval_id) -> ApprovalState:
        return ApprovalState.APPROVED

    async def cancel(self, approval_id, *, reason: str) -> None:
        return None


LEASE = 0.2
MODEL = LLMModel(provider="fake", model_name="fake-1")


class Gate:
    def __init__(self) -> None:
        self.calls: Counter[str] = Counter()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.block_model = False
        self.block_tool = False


class Provider(LLMProvider):
    """Asks for ``send_email`` (if allowed) and then answers; can block mid-call."""

    def __init__(self, gate: Gate) -> None:
        self._gate = gate

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (MODEL,)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self._gate.calls["model"] += 1
        if self._gate.block_model:
            self._gate.entered.set()
            await self._gate.release.wait()
        if request.tools and request.messages[-1].role is not MessageRole.TOOL:
            return LLMResponse(content=None, model=request.model, tool_calls=(ToolCall(call_id="c1", name="send_email", arguments={"to": "a@example.com"}),))
        return LLMResponse(content="Done.", model=request.model)


class Runtime:
    def __init__(self, factory, name: str, gate: Gate) -> None:
        self.gate = gate
        bus = EventBus()
        self.registry = AgentRegistry(bus, SqlAlchemyAgentRepository(factory))
        self.agents = AgentManager(self.registry, bus, SqlAlchemySessionRepository(factory))
        tool_registry = ToolRegistry(bus)
        self.tools = ToolRuntimeManager(tool_registry, ToolExecutor(tool_registry, bus), bus, approvals=ApprovedForThisTest())
        providers = LLMProviderRegistry()
        providers.register(Provider(gate))
        self.interaction = AgentInteractionService(self.registry, self.agents, LLMManager(providers, bus), tool_manager=self.tools)
        executor = ExecutionExecutor(0)
        executor.set_tool_manager(self.tools)
        executor.register_handler(CHAT_KIND, ChatWorkHandler(self.interaction, self.agents))
        self.executions = ExecutionManager(self.registry, executor, SqlAlchemyExecutionRepository(factory), bus, worker_id=name, lease_seconds=LEASE)

    async def start(self) -> "Runtime":
        async def send_email(request: ToolRequest) -> ToolResult:
            self.gate.calls["send_email"] += 1
            if self.gate.block_tool:
                self.gate.entered.set()
                await self.gate.release.wait()
            return ToolResult(status=ToolResultStatus.COMPLETED, output="sent")

        await self.tools.register(Tool(definition=ToolMetadata(name="send_email", description="Send an email.", side_effects=True, parameters={"type": "object", "properties": {"to": {"type": "string"}}, "required": ["to"]}), handler=send_email))
        await self.agents.restore_agents()
        return self

    async def agent(self, tools: tuple[str, ...] = ("send_email",)):
        agent = await self.agents.create_agent(name="Assistant", description="d", type="t", llm_model=MODEL, allowed_tools=tools)
        await self.agents.initialize_agent(agent.id)
        return agent.id

    async def chat(self, agent_id, message: str = "Email the report"):
        session_id = await self.interaction.prepare(agent_id)
        return await self.executions.execute_and_wait(agent_id, metadata=chat_metadata(message, session_id))

    async def crash(self, *pending: asyncio.Task) -> None:
        """Stop without writing anything more, like a killed process."""
        manager = self.executions
        manager._closing = True
        tasks = [*manager._running.values(), *([manager._dispatcher] if manager._dispatcher else []), *pending]
        for execution_id in list(manager._running):
            manager._cancel_requested.add(execution_id)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def only_execution(runtime: Runtime, agent_id):
    (execution,) = await runtime.executions.list_executions(agent_id)
    return execution


@pytest.mark.asyncio
async def test_crash_during_a_side_effecting_tool_needs_a_decision(session_factory) -> None:
    gate = Gate(); gate.block_tool = True
    a = await Runtime(session_factory, "worker-a", gate).start()
    agent_id = await a.agent()
    waiting = asyncio.create_task(a.chat(agent_id))
    await gate.entered.wait()
    await a.crash(waiting)
    await asyncio.sleep(LEASE * 1.5)

    b = await Runtime(session_factory, "worker-b", gate).start()
    await b.executions.recover()

    execution = await only_execution(b, agent_id)
    assert execution.status is S.INTERRUPTED
    assert execution.checkpoint["tools_started"] == [{"name": "send_email", "call_id": "c1", "side_effects": True}]
    assert b.executions.retry_decision(execution).requires_acknowledgement
    with pytest.raises(ExecutionRetryError):
        await b.executions.retry_execution(execution.execution_id)
    assert gate.calls["send_email"] == 1  # never repeated automatically
    assert (await b.agents.get_session(agent_id)).messages == ()  # no half turn
    assert b.registry.get(agent_id).status is AgentStatus.IDLE


@pytest.mark.asyncio
async def test_crash_during_the_model_call_retries_without_confirmation(session_factory) -> None:
    gate = Gate(); gate.block_model = True
    a = await Runtime(session_factory, "worker-a", gate).start()
    agent_id = await a.agent(tools=())
    waiting = asyncio.create_task(a.chat(agent_id, "Hello"))
    await gate.entered.wait()
    await a.crash(waiting)
    await asyncio.sleep(LEASE * 1.5)

    gate.block_model = False
    b = await Runtime(session_factory, "worker-b", gate).start()
    await b.executions.start()
    interrupted = await only_execution(b, agent_id)
    assert interrupted.status is S.INTERRUPTED
    assert not b.executions.retry_decision(interrupted).requires_acknowledgement

    retry = await b.executions.retry_execution(interrupted.execution_id)
    for _ in range(200):
        if (await b.executions.get_execution(retry.execution_id)).status is S.COMPLETED:
            break
        await asyncio.sleep(0.01)
    messages = (await b.agents.get_session(agent_id)).messages
    assert [m.content for m in messages] == ["Hello", "Done."]
    assert {m.metadata["interaction_id"] for m in messages} == {str(retry.execution_id)}
    await b.executions.shutdown()


@pytest.mark.asyncio
async def test_turn_saved_just_before_a_crash_is_reconciled_not_repeated(session_factory) -> None:
    gate = Gate()
    a = await Runtime(session_factory, "worker-a", gate).start()
    agent_id = await a.agent(tools=())
    finished, _ = await a.chat(agent_id, "Hello")
    await a.executions.shutdown()
    # Simulate dying after the session commit but before the execution was marked done.
    repository = SqlAlchemyExecutionRepository(session_factory)
    await repository.transition(
        finished,
        replace(finished, status=S.RUNNING, result=None, finished_at=None, lease_owner="worker-a", lease_expires_at=datetime.now(UTC) - timedelta(seconds=1)),
    )

    b = await Runtime(session_factory, "worker-b", gate).start()
    (recovered,) = await b.executions.recover()

    assert recovered.status is S.COMPLETED
    assert recovered.result is not None and recovered.result.output == "Done."
    assert "already saved" in [t.detail for t in await b.executions.execution_history(finished.execution_id)][-1]
    assert not b.executions.retry_decision(recovered).allowed
    assert len((await b.agents.get_session(agent_id)).messages) == 2
    assert gate.calls["model"] == 1


@pytest.mark.asyncio
async def test_cancelling_a_running_chat_frees_the_agent(session_factory) -> None:
    """Regression: CancelledError bypassed cleanup and left the Agent RUNNING forever."""
    gate = Gate(); gate.block_model = True
    a = await Runtime(session_factory, "worker-a", gate).start()
    agent_id = await a.agent(tools=())
    waiting = asyncio.create_task(a.chat(agent_id, "Hello"))
    await gate.entered.wait()
    running = await only_execution(a, agent_id)

    cancelled = await a.executions.cancel_execution(running.execution_id)

    assert cancelled.status is S.CANCELLED
    with pytest.raises(ExecutionAbortedError):
        await waiting
    assert a.registry.get(agent_id).status is AgentStatus.IDLE
    assert (await a.agents.get_session(agent_id)).messages == ()
    await a.executions.shutdown()


@pytest.mark.asyncio
async def test_a_queued_chat_runs_after_a_restart(session_factory) -> None:
    gate = Gate()
    a = await Runtime(session_factory, "worker-a", gate).start()
    agent_id = await a.agent(tools=())
    session_id = await a.interaction.prepare(agent_id)
    queued = await a.executions.create_execution(agent_id, metadata=chat_metadata("Hello", session_id))

    b = await Runtime(session_factory, "worker-b", gate).start()
    await b.executions.start()
    for _ in range(200):
        if (await b.executions.get_execution(queued.execution_id)).status is S.COMPLETED:
            break
        await asyncio.sleep(0.01)

    assert (await b.executions.get_execution(queued.execution_id)).status is S.COMPLETED
    assert [m.content for m in (await b.agents.get_session(agent_id, session_id)).messages] == ["Hello", "Done."]
    await b.executions.shutdown()
