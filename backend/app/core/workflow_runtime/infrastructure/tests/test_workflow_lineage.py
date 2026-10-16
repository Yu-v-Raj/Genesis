"""Workflow runs keep a durable timeline, and a worker that lost its lease can never
overwrite the state of the worker that took over."""

import asyncio
from collections import Counter
from datetime import timedelta
from uuid import uuid4

import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.pagination import PageCursor
from backend.app.core.core_services.persistence import PersistenceConflictError
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_metadata import ToolMetadata
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus
from backend.app.core.workflow_runtime.application.in_memory_repository import InMemoryWorkflowRepository
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.domain.models import (
    Workflow,
    WorkflowDefinition,
    WorkflowStatus as RS,
    WorkflowTask,
    WorkflowTaskStatus as TS,
    utc_now,
)
from backend.app.core.workflow_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyWorkflowRepository


SCHEMA = {"type": "object", "properties": {"step": {"type": "string"}}, "required": ["step"]}
LONG_LEASE = 30.0  # never expires on its own during a test; expiry is forced explicitly


class Calls:
    """Each tool call gets a number; a test can hold chosen calls open and release them."""

    def __init__(self) -> None:
        self.count: Counter[str] = Counter()
        self.entered: dict[int, asyncio.Event] = {}
        self.release: dict[int, asyncio.Event] = {}
        self.hold: set[int] = set()
        self.total = 0

    def gate(self, number: int) -> tuple[asyncio.Event, asyncio.Event]:
        return self.entered.setdefault(number, asyncio.Event()), self.release.setdefault(number, asyncio.Event())

    async def run(self, request: ToolRequest) -> ToolResult:
        self.total += 1
        number = self.total
        self.count[str(request.arguments["step"])] += 1
        if number in self.hold:
            entered, release = self.gate(number)
            entered.set()
            await release.wait()
        return ToolResult(status=ToolResultStatus.COMPLETED, output={"call": number})


async def manager(repository, worker: str, calls: Calls) -> WorkflowManager:
    bus = EventBus()
    registry = ToolRegistry(bus)
    tools = ToolRuntimeManager(registry, ToolExecutor(registry, bus), bus)
    await tools.register(Tool(definition=ToolMetadata(name="transform", description="t", side_effects=False, parameters=SCHEMA), handler=calls.run))
    return WorkflowManager(tools, bus, repository=repository, worker_id=worker, lease_seconds=LONG_LEASE)


def step(task_id: str, *deps: str) -> WorkflowTask:
    return WorkflowTask(task_id=task_id, name=task_id, configuration={"tool_name": "transform", "tool_arguments": {"step": task_id}}, dependencies=deps)


async def until(source: WorkflowManager, run_id, *statuses: RS, timeout: float = 5.0) -> Workflow:
    deadline = asyncio.get_running_loop().time() + timeout
    while (run := await source.get(run_id)).status not in statuses:
        assert asyncio.get_running_loop().time() < deadline, f"run stayed {run.status}"
        await asyncio.sleep(0.005)
    return run


async def expire_lease(repository, run_id) -> None:
    """The owner stopped renewing (e.g. it froze): its lease is now in the past."""
    current = await repository.get_run(run_id)
    await repository.save_run(current, current.with_updates(lease_expires_at=utc_now() - timedelta(seconds=1)))


def repositories(session_factory):
    return {"memory": InMemoryWorkflowRepository(), "sql": SqlAlchemyWorkflowRepository(session_factory)}


# --------------------------------------------------------------------- timeline


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_every_run_and_step_status_change_is_recorded_in_order(session_factory, kind: str) -> None:
    repository = repositories(session_factory)[kind]
    calls = Calls()
    workflows = await manager(repository, "worker-1", calls)
    run = await workflows.create(name="pipeline", tasks=(step("load"), step("save", "load")))
    await workflows.start(run.workflow_id)
    await until(workflows, run.workflow_id, RS.COMPLETED)
    await workflows.shutdown()

    timeline = await workflows.transitions(run.workflow_id)
    assert [entry.sequence for entry in timeline] == list(range(1, len(timeline) + 1))
    run_changes = [(e.from_status, e.to_status) for e in timeline if e.step_id is None]
    assert run_changes == [(None, "created"), ("created", "queued"), ("queued", "running"), ("running", "completed")]
    for step_id in ("load", "save"):
        assert [(e.from_status, e.to_status) for e in timeline if e.step_id == step_id] == [
            ("pending", "ready"), ("ready", "running"), ("running", "completed"),
        ]
    claimed = next(e for e in timeline if e.to_status == "running" and e.step_id is None)
    assert claimed.worker == "worker-1" and claimed.attempt == 1
    load_done = max(e.sequence for e in timeline if e.step_id == "load")
    save_ready = min(e.sequence for e in timeline if e.step_id == "save")
    assert load_done < save_ready  # dependency order is visible in the timeline


@pytest.mark.asyncio
async def test_a_refused_compare_and_set_records_no_transition(session_factory) -> None:
    repository = SqlAlchemyWorkflowRepository(session_factory)
    definition = WorkflowDefinition(name="w", tasks=(step("a"),))
    await repository.add_definition(definition)
    run = await repository.add_run(definition.new_run())
    queued = await repository.save_run(run, run.with_updates(status=RS.QUEUED))

    with pytest.raises(PersistenceConflictError):
        await repository.save_run(run, run.with_updates(status=RS.CANCELLED))  # stale version
    assert [(e.from_status, e.to_status) for e in await repository.history(run.workflow_id)] == [(None, "created"), ("created", "queued")]
    assert (await repository.get_run(run.workflow_id)).version == queued.version

    await repository.delete_run(run.workflow_id)
    assert await repository.history(run.workflow_id) == ()  # deleted with its run


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_waiting_runs_are_found_however_old_they_are(session_factory, kind: str) -> None:
    repository = repositories(session_factory)[kind]
    definition = WorkflowDefinition(name="w", tasks=(step("a"),))
    await repository.add_definition(definition)
    oldest = await repository.add_run(definition.new_run())
    oldest = await repository.save_run(oldest, oldest.with_updates(status=RS.WAITING_APPROVAL))
    for _ in range(3):
        await repository.add_run(definition.new_run())

    assert oldest.workflow_id not in {run.workflow_id for run in await repository.list_runs(2)}
    assert [run.workflow_id for run in await repository.runs_with_status((RS.WAITING_APPROVAL,))] == [oldest.workflow_id]

    newest_two = await repository.list_runs(2)
    older = await repository.list_runs(10, before=PageCursor(newest_two[-1].created_at, newest_two[-1].workflow_id))
    assert len(newest_two) + len(older) == 4 and older[-1].workflow_id == oldest.workflow_id


# ------------------------------------------------------------- lease ownership


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_a_worker_that_lost_its_lease_cannot_overwrite_the_new_owner(session_factory, kind: str) -> None:
    repository = repositories(session_factory)[kind]
    calls = Calls()
    calls.hold = {1, 2}
    stale = await manager(repository, "worker-a", calls)
    run = await stale.create(name="convert", tasks=(step("convert"),))
    await stale.start(run.workflow_id)
    first_entered, first_release = calls.gate(1)
    await first_entered.wait()  # worker A is running the step
    stale_worker = stale._workers[run.workflow_id]

    await expire_lease(repository, run.workflow_id)
    owner = await manager(repository, "worker-b", calls)
    await owner.start_worker()  # recovers the expired run and claims it
    second_entered, second_release = calls.gate(2)
    await second_entered.wait()  # worker B is now running the same step
    assert (await owner.get(run.workflow_id)).lease_owner == "worker-b"

    first_release.set()  # A's tool finishes while B still owns the run
    await asyncio.wait_for(stale_worker, timeout=5)
    during = await owner.get(run.workflow_id)
    convert = during.tasks[0]
    assert during.lease_owner == "worker-b" and convert.status is TS.RUNNING and convert.result is None

    second_release.set()
    done = await until(owner, run.workflow_id, RS.COMPLETED)
    assert done.tasks[0].result == {"call": 2}  # B's outcome, never A's
    timeline = await owner.transitions(run.workflow_id)
    taken_over = max(e.sequence for e in timeline if e.worker == "worker-b" and e.to_status == "running" and e.step_id is None)
    assert all(e.worker in {"worker-b", None} for e in timeline if e.sequence > taken_over)
    await owner.shutdown()
    await stale.shutdown()


@pytest.mark.asyncio
async def test_concurrent_workers_run_each_step_exactly_once(session_factory) -> None:
    repository = SqlAlchemyWorkflowRepository(session_factory)
    calls = Calls()
    first, second = await manager(repository, "worker-1", calls), await manager(repository, "worker-2", calls)
    runs = [await first.create(name=f"run-{index}", tasks=(step(f"r{index}-a"), step(f"r{index}-b", f"r{index}-a"))) for index in range(6)]
    for run in runs:
        await first.start(run.workflow_id)
    await asyncio.gather(first.start_worker(), second.start_worker())

    finished = [await until(first, run.workflow_id, RS.COMPLETED) for run in runs]
    assert all(task.status is TS.COMPLETED for run in finished for task in run.tasks)
    assert set(calls.count.values()) == {1} and len(calls.count) == 12
    for run in finished:
        claims = [e for e in await first.transitions(run.workflow_id) if e.step_id is None and e.to_status == "running"]
        assert len(claims) == 1 and claims[0].worker in {"worker-1", "worker-2"}
    await asyncio.gather(first.shutdown(), second.shutdown())


@pytest.mark.asyncio
async def test_resume_ready_does_not_depend_on_the_recent_run_list() -> None:
    class RecentListHidesOldRuns(InMemoryWorkflowRepository):
        async def list_runs(self, limit: int = 200, *, before=None):
            return ()

    calls = Calls()
    repository = RecentListHidesOldRuns()
    workflows = await manager(repository, "worker-1", calls)
    decided = uuid4()

    async def approval_state(approval_id):
        from backend.app.core.approval_gateway.domain.approval import ApprovalState
        return ApprovalState.APPROVED if approval_id == decided else ApprovalState.PENDING

    workflows._tools.approval_state = approval_state  # type: ignore[attr-defined]
    definition = await workflows.create_definition(name="w", tasks=(step("a"),))
    run = await repository.add_run(definition.new_run())
    waiting = run.with_updates(status=RS.WAITING_APPROVAL, tasks=(run.tasks[0].with_updates(status=TS.WAITING_APPROVAL, approval_id=decided),))
    await repository.save_run(run, waiting)

    resumed = await workflows.resume_ready()
    assert [item.workflow_id for item in resumed] == [run.workflow_id]
    assert resumed[0].status is RS.QUEUED and resumed[0].tasks[0].status is TS.PENDING
    await workflows.shutdown()
