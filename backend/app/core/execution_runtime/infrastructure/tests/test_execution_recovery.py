"""Failure injection: executions after a worker crash, restart, and shutdown."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyAgentRepository,
    SqlAlchemySessionRepository,
)
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.execution_runtime.application.execution_executor import ExecutionExecutor
from backend.app.core.execution_runtime.application.execution_manager import ExecutionManager
from backend.app.core.execution_runtime.domain.exceptions import ExecutionRetryError
from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus as S
from backend.app.core.execution_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyExecutionRepository
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry


LEASE = 0.2


class GatedExecutor(ExecutionExecutor):
    """Work that blocks until released and counts how often it actually ran."""

    def __init__(self, *, side_effects: bool) -> None:
        super().__init__(0)
        self.side_effects = side_effects
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def may_have_side_effects(self, metadata: Mapping[str, object]) -> bool:
        return self.side_effects

    async def execute(self, context: ExecutionContext) -> str:
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return "done"


class Runtime:
    """One backend process: services over the shared database."""

    def __init__(self, factory, name: str, executor: ExecutionExecutor) -> None:
        self.events: list[str] = []
        bus = EventBus()
        bus.subscribe(lambda event: self.events.append(event.event_type))
        self.registry = AgentRegistry(bus, SqlAlchemyAgentRepository(factory))
        self.agents = AgentManager(self.registry, bus, SqlAlchemySessionRepository(factory))
        self.executor = executor
        self.executions = ExecutionManager(
            self.registry, executor, SqlAlchemyExecutionRepository(factory), bus, worker_id=name, lease_seconds=LEASE
        )

    async def restore(self) -> "Runtime":
        await self.agents.restore_agents()
        return self

    async def crash(self) -> None:
        """Die without writing anything more: no completion, no interruption record."""
        manager = self.executions
        manager._closing = True
        if manager._dispatcher is not None:
            manager._dispatcher.cancel()
        for execution_id, task in list(manager._running.items()):
            manager._cancel_requested.add(execution_id)  # suppress the graceful path
            task.cancel()
        tasks = [*manager._running.values(), *([manager._dispatcher] if manager._dispatcher else [])]
        await asyncio.gather(*tasks, return_exceptions=True)


async def first_runtime(factory, executor: ExecutionExecutor):
    runtime = await Runtime(factory, "worker-a", executor).restore()
    agent = await runtime.agents.create_agent(name="worker", description="d", type="t")
    await runtime.agents.initialize_agent(agent.id)
    return runtime, agent.id


async def wait_for(manager: ExecutionManager, execution_id, status: S, timeout: float = 3.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        execution = await manager.get_execution(execution_id)
        if execution.status is status:
            return execution
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"{execution_id} stayed {execution.status}, expected {status}")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_running_work_is_interrupted_not_rerun_and_retry_needs_acknowledgement(session_factory) -> None:
    a, agent_id = await first_runtime(session_factory, GatedExecutor(side_effects=True))
    execution = await a.executions.execute(agent_id, metadata={"job": "send-invoice"})
    await a.executor.started.wait()
    await a.crash()

    b = await Runtime(session_factory, "worker-b", GatedExecutor(side_effects=True)).restore()
    assert await b.executions.recover() == ()  # the dead worker's lease has not expired yet
    assert (await b.executions.get_execution(execution.execution_id)).status is S.RUNNING

    await asyncio.sleep(LEASE * 1.5)
    (interrupted,) = await b.executions.recover()
    assert (interrupted.status, interrupted.error_category) == (S.INTERRUPTED, "interrupted")
    assert "outcome is unknown" in (interrupted.error or "")
    assert b.executor.calls == 0  # never re-run automatically
    assert "execution.interrupted" in b.events
    timeline = [t.to_status for t in await b.executions.execution_history(execution.execution_id)]
    assert timeline == [S.PENDING, S.QUEUED, S.STARTING, S.RUNNING, S.INTERRUPTED]

    with pytest.raises(ExecutionRetryError) as caught:
        await b.executions.retry_execution(execution.execution_id)
    assert caught.value.requires_acknowledgement

    b.executor.release.set()
    retried = await b.executions.retry_execution(execution.execution_id, acknowledge_side_effects=True)
    assert (retried.attempt, retried.retry_of, dict(retried.metadata)) == (2, execution.execution_id, {"job": "send-invoice"})
    await wait_for(b.executions, retried.execution_id, S.COMPLETED)
    assert (await b.executions.get_execution(execution.execution_id)).status is S.INTERRUPTED
    await b.executions.shutdown()


@pytest.mark.asyncio
async def test_side_effect_free_interrupted_work_retries_without_confirmation(session_factory) -> None:
    a, agent_id = await first_runtime(session_factory, GatedExecutor(side_effects=False))
    execution = await a.executions.execute(agent_id)
    await a.executor.started.wait()
    await a.crash()
    await asyncio.sleep(LEASE * 1.5)

    b = await Runtime(session_factory, "worker-b", GatedExecutor(side_effects=False)).restore()
    await b.executions.recover()
    b.executor.release.set()
    retried = await b.executions.retry_execution(execution.execution_id)

    await wait_for(b.executions, retried.execution_id, S.COMPLETED)
    await b.executions.shutdown()


@pytest.mark.asyncio
async def test_claimed_but_unstarted_and_queued_work_resume_after_restart(session_factory) -> None:
    executor = GatedExecutor(side_effects=True)
    a, agent_id = await first_runtime(session_factory, executor)
    queued = await a.executions.create_execution(agent_id)  # never dispatched
    claimed_only = await a.executions.create_execution(agent_id)
    repository = SqlAlchemyExecutionRepository(session_factory)
    claimed = await repository.claim_next("dead-worker", datetime.now(UTC) + timedelta(seconds=LEASE))
    assert claimed is not None and claimed.execution_id == queued.execution_id  # oldest first
    await asyncio.sleep(LEASE * 1.5)

    b = await Runtime(session_factory, "worker-b", GatedExecutor(side_effects=True)).restore()
    b.executor.release.set()
    await b.executions.start()

    for execution in (queued, claimed_only):
        await wait_for(b.executions, execution.execution_id, S.COMPLETED)
    assert b.executor.calls == 2
    assert "execution.recovered" in b.events
    details = [t.detail for t in await b.executions.execution_history(queued.execution_id)]
    assert "recovered: claimed but never started, returned to the queue" in details
    await b.executions.shutdown()


@pytest.mark.asyncio
async def test_graceful_shutdown_records_interrupted_work(session_factory) -> None:
    a, agent_id = await first_runtime(session_factory, GatedExecutor(side_effects=True))
    execution = await a.executions.execute(agent_id)
    await a.executor.started.wait()

    await a.executions.shutdown(grace_seconds=0.05)

    stored = await a.executions.get_execution(execution.execution_id)
    assert stored.status is S.INTERRUPTED
    assert stored.lease_owner is None


@pytest.mark.asyncio
async def test_cancel_wins_over_a_late_completion(session_factory) -> None:
    a, agent_id = await first_runtime(session_factory, GatedExecutor(side_effects=False))
    execution = await a.executions.execute(agent_id)
    await a.executor.started.wait()

    cancelled = await a.executions.cancel_execution(execution.execution_id)
    a.executor.release.set()
    await asyncio.sleep(0.05)

    assert cancelled.status is S.CANCELLED
    assert (await a.executions.get_execution(execution.execution_id)).status is S.CANCELLED
    await a.executions.shutdown()


@pytest.mark.asyncio
async def test_unregistered_tool_work_fails_safely_through_tool_runtime(session_factory) -> None:
    bus = EventBus()
    registry = ToolRegistry(bus)
    executor = ExecutionExecutor(0)
    executor.set_tool_manager(ToolRuntimeManager(registry, ToolExecutor(registry, bus), bus))
    a, agent_id = await first_runtime(session_factory, executor)

    execution = await a.executions.execute(agent_id, metadata={"tool_name": "delete_everything"})
    failed = await wait_for(a.executions, execution.execution_id, S.FAILED)

    assert failed.error_category == "tool_failed"
    assert executor.may_have_side_effects({"tool_name": "delete_everything"})  # unknown => assume effects
    await a.executions.shutdown()
