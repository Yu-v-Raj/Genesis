"""Bounded in-memory ExecutionRepository, the default when no database is wired in."""

from collections import deque
from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID

from backend.app.core.core_services.persistence import PersistenceConflictError
from backend.app.core.execution_runtime.application.repositories import ExecutionRepository
from backend.app.core.execution_runtime.domain.exceptions import ExecutionNotFoundError
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus
from backend.app.core.execution_runtime.domain.transition import ExecutionTransition


_LEASED = {ExecutionStatus.STARTING, ExecutionStatus.RUNNING}


class ExecutionHistory(ExecutionRepository):
    """Keep the newest executions in memory; nothing survives a restart."""

    def __init__(self, capacity: int = 1000) -> None:
        if capacity < 1:
            raise ValueError("Execution history capacity must be positive.")
        self._capacity = capacity
        self._items: deque[UUID] = deque()
        self._executions: dict[UUID, Execution] = {}
        self._timeline: dict[UUID, list[ExecutionTransition]] = {}
        self._lock = RLock()

    async def add(self, execution: Execution, *, detail: str | None = None) -> Execution:
        stored = replace(execution, version=1)
        with self._lock:
            self._items.appendleft(stored.execution_id)
            self._executions[stored.execution_id] = stored
            self._timeline[stored.execution_id] = []
            self._record(None, stored, detail)
            while len(self._items) > self._capacity:
                evicted = self._items.pop()
                self._executions.pop(evicted, None)
                self._timeline.pop(evicted, None)
        return stored

    async def transition(
        self, current: Execution, updated: Execution, *, detail: str | None = None
    ) -> Execution:
        with self._lock:
            stored = self._executions.get(current.execution_id)
            if stored is None:
                raise ExecutionNotFoundError(current.execution_id)
            if stored.version != current.version:
                raise PersistenceConflictError("The execution changed concurrently.")
            saved = replace(updated, version=current.version + 1)
            self._executions[saved.execution_id] = saved
            if saved.status is not stored.status:
                self._record(stored.status, saved, detail)
            return saved

    async def get(self, execution_id: UUID) -> Execution | None:
        with self._lock:
            return self._executions.get(execution_id)

    async def list(self, agent_id: UUID | None = None, limit: int = 200) -> tuple[Execution, ...]:
        with self._lock:
            items = [self._executions[execution_id] for execution_id in self._items]
        items = [item for item in items if agent_id is None or item.agent_id == agent_id]
        return tuple(items[:limit])

    async def history(self, execution_id: UUID) -> tuple[ExecutionTransition, ...]:
        with self._lock:
            return tuple(self._timeline.get(execution_id, ()))

    async def claim_next(self, owner: str, lease_expires_at: datetime) -> Execution | None:
        with self._lock:
            queued = [self._executions[i] for i in reversed(self._items) if self._executions[i].status is ExecutionStatus.QUEUED]
            if not queued:
                return None
            current = queued[0]
            claimed = replace(
                current.with_status(ExecutionStatus.STARTING, lease_owner=owner, lease_expires_at=lease_expires_at),
                version=current.version + 1,
            )
            self._executions[claimed.execution_id] = claimed
            self._record(current.status, claimed, "claimed by worker")
            return claimed

    async def renew_lease(self, execution_id: UUID, owner: str, lease_expires_at: datetime) -> bool:
        with self._lock:
            stored = self._executions.get(execution_id)
            if stored is None or stored.lease_owner != owner or stored.status not in _LEASED:
                return False
            self._executions[execution_id] = replace(stored, lease_expires_at=lease_expires_at)
            return True

    async def expired_leases(self, now: datetime) -> tuple[Execution, ...]:
        with self._lock:
            return tuple(
                e
                for e in self._executions.values()
                if e.status in _LEASED and (e.lease_expires_at is None or e.lease_expires_at < now)
            )

    def _record(self, previous: ExecutionStatus | None, execution: Execution, detail: str | None) -> None:
        timeline = self._timeline.setdefault(execution.execution_id, [])
        timeline.append(
            ExecutionTransition(
                execution_id=execution.execution_id,
                sequence=len(timeline) + 1,
                from_status=previous,
                to_status=execution.status,
                at=execution.updated_at or datetime.now(UTC),
                detail=detail,
            )
        )
