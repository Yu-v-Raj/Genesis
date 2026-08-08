"""Lifecycle orchestration for independent Agent execution records."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.execution_runtime.application.execution_executor import ExecutionExecutor
from backend.app.core.execution_runtime.application.execution_history import ExecutionHistory
from backend.app.core.execution_runtime.domain.exceptions import (
    AgentNotExecutableError,
    ExecutionLifecycleError,
)
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext
from backend.app.core.execution_runtime.domain.execution_result import ExecutionResult
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus
from backend.app.core.observability.domain.events import (
    Event,
    ExecutionCancelled,
    ExecutionCompleted,
    ExecutionCreated,
    ExecutionFailed,
    ExecutionProgress,
    ExecutionQueued,
    ExecutionStarted,
)


class ExecutionManager:
    """Own the lifecycle, contexts, tasks, history, and events for executions."""

    _ALLOWED_TRANSITIONS = {
        ExecutionStatus.PENDING: {ExecutionStatus.QUEUED, ExecutionStatus.CANCELLED},
        ExecutionStatus.QUEUED: {ExecutionStatus.STARTING, ExecutionStatus.CANCELLED},
        ExecutionStatus.STARTING: {ExecutionStatus.RUNNING, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED},
        ExecutionStatus.RUNNING: {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED},
        ExecutionStatus.COMPLETED: set(),
        ExecutionStatus.FAILED: set(),
        ExecutionStatus.CANCELLED: set(),
    }

    def __init__(
        self,
        agent_registry: AgentRegistry,
        executor: ExecutionExecutor,
        history: ExecutionHistory,
        event_bus: EventBus,
    ) -> None:
        self._agent_registry = agent_registry
        self._executor = executor
        self._history = history
        self._event_bus = event_bus
        self._contexts: dict[UUID, ExecutionContext] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def create_execution(
        self, agent_id: UUID, *, metadata: Mapping[str, object] | None = None
    ) -> Execution:
        """Validate an Agent and create a queued execution without changing Agent lifecycle."""
        self._require_executable_agent(agent_id)
        execution = Execution(agent_id=agent_id, metadata={} if metadata is None else metadata)
        async with self._lock:
            self._history.save(execution)
            self._contexts[execution.execution_id] = ExecutionContext(
                execution_id=execution.execution_id, agent_id=agent_id, metadata=execution.metadata
            )
        await self._publish(ExecutionCreated, execution)
        await self._transition(execution.execution_id, ExecutionStatus.QUEUED, ExecutionQueued)
        return self.get_execution(execution.execution_id)

    async def start_execution(self, execution_id: UUID) -> Execution:
        """Schedule a queued execution and return its current immutable snapshot."""
        await self._transition(execution_id, ExecutionStatus.STARTING)
        async with self._lock:
            execution = self._history.get(execution_id)
            self._tasks[execution_id] = asyncio.create_task(self._run(execution_id))
        return execution

    async def execute(self, agent_id: UUID, *, metadata: Mapping[str, object] | None = None) -> Execution:
        """Create and asynchronously start an execution request."""
        execution = await self.create_execution(agent_id, metadata=metadata)
        return await self.start_execution(execution.execution_id)

    async def cancel_execution(self, execution_id: UUID) -> Execution:
        """Cancel a non-terminal execution, requesting cancellation of active work."""
        async with self._lock:
            execution = self._history.get(execution_id)
            context = self._contexts.get(execution_id)
            if context is not None:
                self._contexts[execution_id] = ExecutionContext(
                    execution_id=context.execution_id,
                    agent_id=context.agent_id,
                    current_step=context.current_step,
                    variables=context.variables,
                    metadata=context.metadata,
                    cancel_requested=True,
                )
            task = self._tasks.get(execution_id)
        cancelled = await self._transition(execution_id, ExecutionStatus.CANCELLED, ExecutionCancelled)
        if task is not None and not task.done():
            task.cancel()
        return cancelled

    async def complete_execution(self, execution_id: UUID, output: str) -> Execution:
        """Mark an active execution completed with its immutable result."""
        return await self._finish(execution_id, ExecutionStatus.COMPLETED, output=output)

    async def fail_execution(self, execution_id: UUID, error: str) -> Execution:
        """Mark an active execution failed with a stable error message."""
        return await self._finish(execution_id, ExecutionStatus.FAILED, error=error)

    def get_execution(self, execution_id: UUID) -> Execution:
        """Look up one execution in bounded history."""
        return self._history.get(execution_id)

    def list_executions(self, agent_id: UUID | None = None) -> tuple[Execution, ...]:
        """Return newest-first execution history, optionally for one Agent."""
        return self._history.list(agent_id)

    async def _run(self, execution_id: UUID) -> None:
        try:
            await self._transition(execution_id, ExecutionStatus.RUNNING, ExecutionStarted)
            await self._publish(ExecutionProgress, self.get_execution(execution_id), step="executing")
            context = self._contexts[execution_id]
            output = await self._executor.execute(context)
            if self._contexts[execution_id].cancel_requested:
                return
            await self.complete_execution(execution_id, output)
        except asyncio.CancelledError:
            return
        except Exception as error:  # Executor implementations may fail in future phases.
            try:
                await self.fail_execution(execution_id, str(error))
            except ExecutionLifecycleError:
                pass
        finally:
            async with self._lock:
                self._tasks.pop(execution_id, None)

    async def _finish(
        self, execution_id: UUID, status: ExecutionStatus, output: str | None = None, error: str | None = None
    ) -> Execution:
        async with self._lock:
            execution = self._history.get(execution_id)
            self._require_transition(execution, status)
            finished_at = datetime.now(UTC)
            result = ExecutionResult(
                status=status,
                output=output,
                duration=max(0.0, (finished_at - (execution.started_at or finished_at)).total_seconds()),
            )
            updated = execution.with_status(
                status, finished_at=finished_at, result=result, error=error
            )
            self._history.save(updated)
            self._contexts.pop(execution_id, None)
        await self._publish(ExecutionCompleted if status is ExecutionStatus.COMPLETED else ExecutionFailed, updated)
        return updated

    async def _transition(
        self,
        execution_id: UUID,
        target: ExecutionStatus,
        event_type: type[Event] | None = None,
    ) -> Execution:
        async with self._lock:
            execution = self._history.get(execution_id)
            self._require_transition(execution, target)
            updates: dict[str, object] = {}
            if target is ExecutionStatus.RUNNING:
                updates["started_at"] = datetime.now(UTC)
            updated = execution.with_status(target, **updates)
            self._history.save(updated)
        if event_type is not None:
            await self._publish(event_type, updated)
        return updated

    def _require_executable_agent(self, agent_id: UUID) -> None:
        agent = self._agent_registry.get(agent_id)
        if agent.status is AgentStatus.STOPPED:
            raise AgentNotExecutableError(agent_id, "it is stopped")
        if agent.status in {AgentStatus.CREATED, AgentStatus.INITIALIZING}:
            raise AgentNotExecutableError(agent_id, "it is not initialized")

    def _require_transition(self, execution: Execution, target: ExecutionStatus) -> None:
        if target not in self._ALLOWED_TRANSITIONS[execution.status]:
            raise ExecutionLifecycleError(execution.execution_id, execution.status.value, target.value)

    async def _publish(
        self, event_type: type[Event], execution: Execution, step: str | None = None
    ) -> None:
        payload: dict[str, object] = {
            "execution_id": str(execution.execution_id),
            "agent_id": str(execution.agent_id),
            "status": execution.status.value,
        }
        if step is not None:
            payload["step"] = step
        await self._event_bus.publish(event_type(source="execution_manager", payload=payload))
