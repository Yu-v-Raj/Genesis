"""Durable lifecycle orchestration and worker for independent Agent executions.

The repository is the queue. A worker claims QUEUED work with an atomic conditional
update and holds a renewable lease while it runs it. Every transition is persisted
(compare-and-set) before its event is published, so the database is authoritative and
events are best-effort notifications.

Recovery (at startup and on every dispatcher tick) only touches executions whose lease
expired, i.e. whose worker stopped renewing:

- STARTING (claimed, work not begun) -> back to QUEUED and run again; nothing happened yet.
- RUNNING (work may have begun) -> INTERRUPTED. Genesis cannot know whether an external
  effect already happened, so it never re-runs this automatically. A user may retry it,
  which creates a new linked attempt; for work that may have side effects the retry must
  be explicitly acknowledged.
"""

import asyncio
import os
import socket
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.execution_runtime.application.execution_executor import ExecutionExecutor
from backend.app.core.execution_runtime.application.execution_history import ExecutionHistory
from backend.app.core.execution_runtime.application.repositories import ExecutionRepository
from backend.app.core.execution_runtime.domain.exceptions import (
    AgentNotExecutableError,
    ExecutionLifecycleError,
    ExecutionNotFoundError,
    ExecutionRetryError,
)
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext
from backend.app.core.execution_runtime.domain.execution_result import ExecutionResult
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus
from backend.app.core.execution_runtime.domain.lifecycle import (
    RetryDecision,
    can_transition,
    retry_decision,
)
from backend.app.core.execution_runtime.domain.transition import ExecutionTransition
from backend.app.core.observability.domain.events import (
    Event,
    ExecutionCancelled,
    ExecutionCompleted,
    ExecutionCreated,
    ExecutionFailed,
    ExecutionInterrupted,
    ExecutionProgress,
    ExecutionQueued,
    ExecutionRecovered,
    ExecutionStarted,
)


INTERRUPTED_MESSAGE = (
    "Genesis stopped before this work finished, so its outcome is unknown. "
    "It was not re-run automatically."
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def default_worker_id() -> str:
    """Identify this process as a lease owner (host, pid, and a per-start nonce)."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


class ExecutionManager:
    """Own the lifecycle, queue, worker, recovery, and events for executions."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        executor: ExecutionExecutor,
        history: ExecutionRepository | None,
        event_bus: EventBus,
        *,
        worker_id: str | None = None,
        lease_seconds: float = 30.0,
        concurrency: int = 4,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("Execution lease duration must be positive.")
        if concurrency < 1:
            raise ValueError("Execution concurrency must be positive.")
        self._agent_registry = agent_registry
        self._executor = executor
        self._repository: ExecutionRepository = history or ExecutionHistory()
        self._event_bus = event_bus
        self._worker_id = worker_id or default_worker_id()
        self._lease = timedelta(seconds=lease_seconds)
        self._tick_seconds = lease_seconds / 3
        self._concurrency = concurrency
        # Transient runtime handles; never persisted.
        self._running: dict[UUID, asyncio.Task[None]] = {}
        self._cancel_requested: set[UUID] = set()
        self._dispatcher: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._closing = False

    @property
    def worker_id(self) -> str:
        return self._worker_id

    # ----------------------------------------------------------------- public API

    async def create_execution(
        self,
        agent_id: UUID,
        *,
        metadata: Mapping[str, object] | None = None,
        attempt: int = 1,
        retry_of: UUID | None = None,
    ) -> Execution:
        """Validate the Agent, persist the execution, and queue it."""
        self._require_executable_agent(agent_id)
        execution = await self._repository.add(
            Execution(
                agent_id=agent_id,
                metadata={} if metadata is None else metadata,
                attempt=attempt,
                retry_of=retry_of,
                updated_at=_utc_now(),
            ),
            detail="created" if retry_of is None else f"retry of {retry_of}",
        )
        await self._publish(ExecutionCreated, execution)
        return await self._transition(execution, ExecutionStatus.QUEUED, ExecutionQueued, detail="queued")

    async def start_execution(self, execution_id: UUID) -> Execution:
        """Make sure a queued execution will be picked up by this process's worker."""
        execution = await self.get_execution(execution_id)
        if execution.status is not ExecutionStatus.QUEUED:
            raise ExecutionLifecycleError(execution_id, execution.status.value, ExecutionStatus.STARTING.value)
        self._ensure_dispatcher()
        return execution

    async def execute(self, agent_id: UUID, *, metadata: Mapping[str, object] | None = None) -> Execution:
        """Create a durable execution request and hand it to the worker."""
        execution = await self.create_execution(agent_id, metadata=metadata)
        self._ensure_dispatcher()
        return execution

    async def cancel_execution(self, execution_id: UUID) -> Execution:
        """Cancel a non-terminal execution and stop its work if this process is running it."""
        current = await self.get_execution(execution_id)
        self._cancel_requested.add(execution_id)
        cancelled = await self._finish(
            current, ExecutionStatus.CANCELLED, ExecutionCancelled, detail="cancelled by request", strict=True
        )
        task = self._running.get(execution_id)
        if task is not None and not task.done():
            task.cancel()
        return cancelled

    async def retry_execution(self, execution_id: UUID, *, acknowledge_side_effects: bool = False) -> Execution:
        """Start a new attempt of a failed, cancelled, or interrupted execution."""
        source = await self.get_execution(execution_id)
        decision = self.retry_decision(source)
        if not decision.allowed:
            raise ExecutionRetryError(decision.reason)
        if decision.requires_acknowledgement and not acknowledge_side_effects:
            raise ExecutionRetryError(decision.reason, requires_acknowledgement=True)
        retried = await self.create_execution(
            source.agent_id, metadata=source.metadata, attempt=source.attempt + 1, retry_of=source.execution_id
        )
        self._ensure_dispatcher()
        return retried

    def retry_decision(self, execution: Execution) -> RetryDecision:
        return retry_decision(
            execution.status, may_have_side_effects=self._executor.may_have_side_effects(execution.metadata)
        )

    async def get_execution(self, execution_id: UUID) -> Execution:
        execution = await self._repository.get(execution_id)
        if execution is None:
            raise ExecutionNotFoundError(execution_id)
        return execution

    async def list_executions(self, agent_id: UUID | None = None) -> tuple[Execution, ...]:
        """Return newest-first executions, optionally for one Agent."""
        return await self._repository.list(agent_id)

    async def execution_history(self, execution_id: UUID) -> tuple[ExecutionTransition, ...]:
        await self.get_execution(execution_id)
        return await self._repository.history(execution_id)

    # ------------------------------------------------------- worker and recovery

    async def start(self) -> None:
        """Recover work left by a previous process, then start the dispatcher."""
        self._closing = False
        await self.recover()
        self._ensure_dispatcher()

    async def shutdown(self, grace_seconds: float = 5.0) -> None:
        """Stop claiming work, let running work finish briefly, then interrupt the rest."""
        self._closing = True
        self._wake.set()
        if self._dispatcher is not None:
            self._dispatcher.cancel()
            await asyncio.gather(self._dispatcher, return_exceptions=True)
            self._dispatcher = None
        running = list(self._running.values())
        if running:
            _, pending = await asyncio.wait(running, timeout=grace_seconds)
            for task in pending:
                task.cancel()
            await asyncio.gather(*running, return_exceptions=True)

    async def recover(self) -> tuple[Execution, ...]:
        """Resolve executions whose worker stopped renewing its lease."""
        recovered: list[Execution] = []
        for stale in await self._repository.expired_leases(_utc_now()):
            if stale.execution_id in self._running:
                continue
            try:
                if stale.status is ExecutionStatus.STARTING:
                    recovered.append(
                        await self._transition(
                            stale,
                            ExecutionStatus.QUEUED,
                            ExecutionRecovered,
                            detail="recovered: claimed but never started, returned to the queue",
                            lease_owner=None,
                            lease_expires_at=None,
                        )
                    )
                elif stale.status is ExecutionStatus.RUNNING:
                    recovered.append(await self._interrupt(stale))
            except PersistenceConflictError:
                continue  # another worker resolved it first
        if recovered:
            self._wake.set()
        return tuple(recovered)

    def _ensure_dispatcher(self) -> None:
        if self._closing:
            return
        if self._dispatcher is None or self._dispatcher.done():
            self._dispatcher = asyncio.create_task(self._dispatch_loop(), name="execution-dispatcher")
        self._wake.set()

    async def _dispatch_loop(self) -> None:
        while not self._closing:
            self._wake.clear()
            try:
                await self._renew_leases()
                await self.recover()
                while len(self._running) < self._concurrency and not self._closing:
                    claimed = await self._repository.claim_next(self._worker_id, self._lease_until())
                    if claimed is None:
                        break
                    task = asyncio.create_task(self._run(claimed), name=f"execution-{claimed.execution_id}")
                    self._running[claimed.execution_id] = task
                    task.add_done_callback(self._on_done(claimed.execution_id))
            except PersistenceError as error:
                logger.error("Execution dispatcher could not reach storage", extra={"genesis_context": {"error": str(error)}})
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._tick_seconds)
            except TimeoutError:
                pass

    def _on_done(self, execution_id: UUID) -> Any:
        def done(_: asyncio.Task[None]) -> None:
            self._running.pop(execution_id, None)
            self._cancel_requested.discard(execution_id)
            self._wake.set()

        return done

    async def _renew_leases(self) -> None:
        until = self._lease_until()
        for execution_id in list(self._running):
            await self._repository.renew_lease(execution_id, self._worker_id, until)

    async def _run(self, claimed: Execution) -> None:
        execution_id = claimed.execution_id
        try:
            # Persisted before any work is invoked: past this point the outcome of an
            # interruption is unknown.
            running = await self._transition(
                claimed,
                ExecutionStatus.RUNNING,
                ExecutionStarted,
                detail="work started",
                started_at=_utc_now(),
                current_step="executing",
            )
            await self._publish(ExecutionProgress, running, step="executing")
            context = ExecutionContext(
                execution_id=execution_id, agent_id=running.agent_id, metadata=running.metadata
            )
            output = await self._executor.execute(context)
            await self._finish(running, ExecutionStatus.COMPLETED, ExecutionCompleted, output=output, detail="completed")
        except asyncio.CancelledError:
            if execution_id not in self._cancel_requested:
                # Shutdown, not a user cancel: record what is known about the work.
                current = await self._repository.get(execution_id)
                if current is not None and current.status is ExecutionStatus.RUNNING:
                    await self._interrupt(current)
                elif current is not None and current.status is ExecutionStatus.STARTING:
                    await self._transition(
                        current,
                        ExecutionStatus.QUEUED,
                        ExecutionRecovered,
                        detail="returned to the queue at shutdown before work started",
                        lease_owner=None,
                        lease_expires_at=None,
                    )
        except (PersistenceConflictError, ExecutionLifecycleError):
            return  # cancelled or resolved elsewhere; never overwrite a newer state
        except Exception as error:
            current = await self._repository.get(execution_id)
            if current is not None:
                await self._finish(
                    current,
                    ExecutionStatus.FAILED,
                    ExecutionFailed,
                    error=str(error),
                    error_category="tool_failed" if "tool_name" in current.metadata else "execution_failed",
                    detail="failed",
                )

    async def _interrupt(self, current: Execution) -> Execution:
        return await self._transition(
            current,
            ExecutionStatus.INTERRUPTED,
            ExecutionInterrupted,
            detail="interrupted: worker stopped while the work was running",
            finished_at=_utc_now(),
            error=INTERRUPTED_MESSAGE,
            error_category="interrupted",
            current_step=None,
            lease_owner=None,
            lease_expires_at=None,
        )

    async def _finish(
        self,
        current: Execution,
        status: ExecutionStatus,
        event_type: type[Event],
        *,
        detail: str,
        output: str | None = None,
        error: str | None = None,
        error_category: str | None = None,
        strict: bool = False,
    ) -> Execution:
        """Move to a terminal state, re-reading once if a concurrent change won the race.

        A terminal state is never overwritten: if the execution already finished, a
        non-strict caller gets the stored record and a strict caller gets an error.
        """
        for _ in range(3):
            if not can_transition(current.status, status):
                if strict:
                    raise ExecutionLifecycleError(current.execution_id, current.status.value, status.value)
                return current
            finished_at = _utc_now()
            started = current.started_at or finished_at
            result = ExecutionResult(
                status=status,
                output=output,
                duration=max(0.0, (finished_at - started).total_seconds()),
            )
            try:
                return await self._transition(
                    current,
                    status,
                    event_type,
                    detail=detail,
                    finished_at=finished_at,
                    result=result,
                    error=error,
                    error_category=error_category,
                    current_step=None,
                    lease_owner=None,
                    lease_expires_at=None,
                )
            except PersistenceConflictError:
                current = await self.get_execution(current.execution_id)
        raise PersistenceConflictError("The execution kept changing; try again.")

    async def _transition(
        self,
        current: Execution,
        target: ExecutionStatus,
        event_type: type[Event] | None = None,
        *,
        detail: str | None = None,
        **changes: object,
    ) -> Execution:
        if not can_transition(current.status, target):
            raise ExecutionLifecycleError(current.execution_id, current.status.value, target.value)
        saved = await self._repository.transition(current, current.with_status(target, **changes), detail=detail)
        if event_type is not None:
            await self._publish(event_type, saved)
        return saved

    def _lease_until(self) -> datetime:
        return _utc_now() + self._lease

    def _require_executable_agent(self, agent_id: UUID) -> None:
        agent = self._agent_registry.get(agent_id)
        if agent.status is AgentStatus.STOPPED:
            raise AgentNotExecutableError(agent_id, "it is stopped")
        if agent.status in {AgentStatus.CREATED, AgentStatus.INITIALIZING}:
            raise AgentNotExecutableError(agent_id, "it is not initialized")

    async def _publish(self, event_type: type[Event], execution: Execution, step: str | None = None) -> None:
        payload: dict[str, object] = {
            "execution_id": str(execution.execution_id),
            "agent_id": str(execution.agent_id),
            "status": execution.status.value,
            "attempt": execution.attempt,
        }
        if execution.retry_of is not None:
            payload["retry_of"] = str(execution.retry_of)
        if step is not None:
            payload["step"] = step
        await self._event_bus.publish(event_type(source="execution_manager", payload=payload))
