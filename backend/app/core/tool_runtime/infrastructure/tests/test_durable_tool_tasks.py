"""Tool task history is durable: written before the tool acts, bounded, correlated, and
closed honestly after a crash (outcome unknown, never re-run)."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest

from backend.app.core.approval_gateway.application.approval_service import ApprovalService
from backend.app.core.approval_gateway.application.in_memory_repository import InMemoryApprovalRepository
from backend.app.core.approval_gateway.domain.approval import ApprovalOutcome, ApprovalState, DecisionSource
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.pagination import PageCursor
from backend.app.core.tool_runtime.application.task_repository import InMemoryToolTaskRepository, TaskQuery
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import INTERRUPTED_TASK_MESSAGE, ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.authorization import AgentToolContext, OperatorTestContext
from backend.app.core.tool_runtime.domain.task import Task, TaskStatus, utc_now
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_metadata import ToolMetadata
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus
from backend.app.core.tool_runtime.infrastructure.sqlalchemy_repository import (
    MAX_STORED_OUTPUT_BYTES,
    SqlAlchemyToolTaskRepository,
)


SCHEMA = {"type": "object", "properties": {"value": {"type": "string"}, "api_key": {"type": "string"}}, "required": ["value"]}
OPERATOR = OperatorTestContext()


class Harness:
    def __init__(self, store, *, approvals: ApprovalService | None = None) -> None:
        self.bus = EventBus()
        self.events: list = []
        self.bus.subscribe(self.events.append)
        registry = ToolRegistry(self.bus)
        self.store = store
        self.tools = ToolRuntimeManager(registry, ToolExecutor(registry, self.bus), self.bus, approvals=approvals, tasks=store)
        self.seen_while_running: list[Task | None] = []
        self.calls = 0

    async def register(self, name: str, *, side_effects: bool = False, output: object = "ok") -> None:
        async def run(request: ToolRequest) -> ToolResult:
            self.calls += 1
            # What storage says at the moment the tool acts.
            self.seen_while_running.append(await self.store.get(request.task_id))
            return ToolResult(status=ToolResultStatus.COMPLETED, output=output)

        await self.tools.register(Tool(definition=ToolMetadata(name=name, description=name, side_effects=side_effects, parameters=SCHEMA), handler=run))


@pytest.mark.asyncio
async def test_a_task_is_stored_as_running_before_the_tool_acts_and_terminal_after(session_factory) -> None:
    harness = Harness(SqlAlchemyToolTaskRepository(session_factory))
    await harness.register("echo_like")
    execution_id = uuid4()
    context = AgentToolContext(agent_id=uuid4(), interaction_id=execution_id, execution_id=execution_id)
    harness.tools.bind_agent_grants(_AllowAll())

    task = await harness.tools.execute(tool_name="echo_like", arguments={"value": "v", "api_key": "sk-abcdefghijklmnop"}, context=context)

    (during,) = harness.seen_while_running
    assert during is not None and during.status is TaskStatus.RUNNING and during.started_at is not None
    stored = await harness.store.get(task.task_id)
    assert stored is not None and stored.status is TaskStatus.COMPLETED and stored.result.output == "ok"
    assert stored.arguments == {"value": "v", "api_key": "[redacted]"}  # never the secret
    assert stored.tool_version == "1.0.0"
    assert stored.metadata["caller"] == "agent" and stored.metadata["execution_id"] == str(execution_id)
    assert (await harness.store.page(TaskQuery(execution_id=execution_id), before=None, limit=10)) == (stored,)


@pytest.mark.asyncio
async def test_history_pages_newest_first_and_filters_by_correlation(session_factory) -> None:
    store = SqlAlchemyToolTaskRepository(session_factory)
    workflow_id, execution_id = uuid4(), uuid4()
    start = utc_now()
    tasks = [
        Task(execution_id=None, tool_name="a", created_at=start + timedelta(seconds=index), metadata=metadata)
        for index, metadata in enumerate(
            [{"workflow_id": str(workflow_id), "workflow_task_id": "s1", "workflow_attempt": 1}, {}, {"caller": "agent"}, {}]
        )
    ]
    tasks.append(Task(execution_id=execution_id, tool_name="b", created_at=start + timedelta(seconds=9)))
    for task in tasks:
        await store.save(task)

    first = await store.page(TaskQuery(), before=None, limit=2)
    second = await store.page(TaskQuery(), before=PageCursor(first[-1].created_at, first[-1].task_id), limit=2)
    third = await store.page(TaskQuery(), before=PageCursor(second[-1].created_at, second[-1].task_id), limit=2)
    assert [t.task_id for t in (*first, *second, *third)] == [t.task_id for t in reversed(tasks)]
    assert [t.task_id for t in await store.page(TaskQuery(workflow_id=workflow_id), before=None, limit=10)] == [tasks[0].task_id]
    assert [t.task_id for t in await store.page(TaskQuery(execution_id=execution_id), before=None, limit=10)] == [tasks[4].task_id]
    assert [t.task_id for t in await store.page(TaskQuery(tool_name="b"), before=None, limit=10)] == [tasks[4].task_id]


@pytest.mark.asyncio
async def test_large_outputs_are_stored_as_a_marked_preview(session_factory) -> None:
    harness = Harness(SqlAlchemyToolTaskRepository(session_factory))
    await harness.register("big", output={"blob": "x" * (MAX_STORED_OUTPUT_BYTES * 2)})
    task = await harness.tools.execute(tool_name="big", arguments={"value": "v"}, context=OPERATOR)

    stored = await harness.store.get(task.task_id)
    assert task.result.output == {"blob": "x" * (MAX_STORED_OUTPUT_BYTES * 2)}  # the caller still gets it all
    assert stored.result.output["truncated"] is True and stored.result.output["bytes"] > MAX_STORED_OUTPUT_BYTES
    assert len(stored.result.output["preview"]) <= 2_000


@pytest.mark.asyncio
async def test_if_the_task_cannot_be_recorded_the_tool_does_not_run_and_the_approval_says_so() -> None:
    approvals = ApprovalService(InMemoryApprovalRepository(), EventBus())
    harness = Harness(_Unwritable(), approvals=approvals)
    await harness.register("effects", side_effects=True)
    held = await harness.tools.authorize(tool_name="effects", arguments={"value": "v"}, context=OPERATOR)
    await approvals.approve(held.approval_id, source=DecisionSource.LOCAL_API)

    with pytest.raises(RuntimeError, match="storage down"):
        await harness.tools.execute(tool_name="effects", arguments={"value": "v"}, context=OPERATOR)

    assert harness.calls == 0
    approval = await approvals.get(held.approval_id)
    assert (approval.state, approval.outcome) == (ApprovalState.CONSUMED, ApprovalOutcome.FAILED)
    assert "could not be recorded" in approval.detail


@pytest.mark.asyncio
async def test_tasks_left_running_by_a_crash_are_closed_as_interrupted_and_never_rerun(session_factory) -> None:
    store = SqlAlchemyToolTaskRepository(session_factory)
    approvals = ApprovalService(InMemoryApprovalRepository(), EventBus())
    first = Harness(store, approvals=approvals)
    await first.register("effects", side_effects=True)
    held = await first.tools.authorize(tool_name="effects", arguments={"value": "v"}, context=OPERATOR)
    await approvals.approve(held.approval_id, source=DecisionSource.LOCAL_API)
    entered, release = asyncio.Event(), asyncio.Event()

    async def hang(request: ToolRequest) -> ToolResult:
        entered.set()
        await release.wait()
        return ToolResult(status=ToolResultStatus.COMPLETED, output="late")

    await first.tools.register(Tool(definition=ToolMetadata(name="hang", description="h", side_effects=False, parameters=SCHEMA), handler=hang))
    call = asyncio.create_task(first.tools.execute(tool_name="hang", arguments={"value": "v"}, context=OPERATOR))
    await entered.wait()
    # The process "dies" here: no terminal snapshot is written for the hanging task.
    (stuck,) = await store.unfinished()
    approved_running = stuck.with_updates(task_id=uuid4(), metadata={"caller": "operator", "approval_id": str(held.approval_id)})
    await store.save(approved_running)
    await approvals.consume(held.approval_id, (await approvals.get(held.approval_id)).operation_digest)

    restarted = Harness(store, approvals=approvals)
    assert await restarted.tools.recover_unfinished() == 2
    for task_id in (stuck.task_id, approved_running.task_id):
        closed = await store.get(task_id)
        assert closed.status is TaskStatus.FAILED and closed.result.error == INTERRUPTED_TASK_MESSAGE
        assert closed.result.metadata == {"interrupted": True} and closed.finished_at is not None
    assert restarted.calls == 0 and await store.unfinished() == ()
    assert (await approvals.get(held.approval_id)).outcome is ApprovalOutcome.UNKNOWN
    assert [e.event_type for e in restarted.events if e.event_type.startswith("task.")] == ["task.failed", "task.failed"]
    assert await restarted.tools.recover_unfinished() == 0  # idempotent

    release.set()
    await call


@pytest.mark.asyncio
async def test_without_a_store_history_stays_in_process() -> None:
    harness = Harness(InMemoryToolTaskRepository())
    await harness.register("plain")
    workflow_free = await harness.tools.execute(tool_name="plain", arguments={"value": "v"}, context=OPERATOR)
    page = await harness.tools.task_page(TaskQuery(tool_name="plain"))
    assert [task.task_id for task in page] == [workflow_free.task_id]
    assert (await harness.tools.get_task(workflow_free.task_id)).status is TaskStatus.COMPLETED


class _AllowAll:
    async def agent_tool_grant(self, agent_id):
        from backend.app.core.tool_runtime.application.authorization_policy import AgentToolGrant

        return AgentToolGrant(allowed_tools=frozenset({"echo_like"}), active=True)


class _Unwritable(InMemoryToolTaskRepository):
    async def save(self, task: Task) -> None:
        raise RuntimeError("storage down")
