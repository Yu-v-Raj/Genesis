"""Bounded in-memory storage for immutable execution snapshots."""

from collections import deque
from threading import RLock
from uuid import UUID

from backend.app.core.execution_runtime.domain.exceptions import ExecutionNotFoundError
from backend.app.core.execution_runtime.domain.execution import Execution


class ExecutionHistory:
    """Keep the newest immutable execution records, replaceable by persistent storage later."""

    def __init__(self, capacity: int = 1000) -> None:
        if capacity < 1:
            raise ValueError("Execution history capacity must be positive.")
        self._capacity = capacity
        self._items: deque[UUID] = deque()
        self._executions: dict[UUID, Execution] = {}
        self._lock = RLock()

    def save(self, execution: Execution) -> Execution:
        """Store or replace an execution, retaining only the newest records."""
        with self._lock:
            if execution.execution_id in self._executions:
                self._items.remove(execution.execution_id)
            self._items.appendleft(execution.execution_id)
            self._executions[execution.execution_id] = execution
            while len(self._items) > self._capacity:
                self._executions.pop(self._items.pop(), None)
        return execution

    def get(self, execution_id: UUID) -> Execution:
        """Return one execution snapshot."""
        with self._lock:
            try:
                return self._executions[execution_id]
            except KeyError as error:
                raise ExecutionNotFoundError(execution_id) from error

    def list(self, agent_id: UUID | None = None) -> tuple[Execution, ...]:
        """Return newest-first snapshots, optionally narrowed to one Agent."""
        with self._lock:
            return tuple(
                execution
                for execution_id in self._items
                if (execution := self._executions[execution_id]).agent_id == agent_id or agent_id is None
            )
