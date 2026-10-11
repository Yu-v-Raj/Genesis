"""Persistence port for durable executions.

Every state change is a compare-and-set on ``Execution.version`` and appends a timeline
entry in the same transaction, so a stale writer can never overwrite newer state
(``PersistenceConflictError``) and the history always matches the record.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.transition import ExecutionTransition


class ExecutionRepository(ABC):
    @abstractmethod
    async def add(self, execution: Execution, *, detail: str | None = None) -> Execution:
        """Insert a new execution (version 1) and its first timeline entry."""

    @abstractmethod
    async def transition(
        self, current: Execution, updated: Execution, *, detail: str | None = None
    ) -> Execution:
        """Store ``updated`` only if the stored version still equals ``current.version``."""

    @abstractmethod
    async def get(self, execution_id: UUID) -> Execution | None: ...

    @abstractmethod
    async def list(self, agent_id: UUID | None = None, limit: int = 200) -> tuple[Execution, ...]:
        """Newest first."""

    @abstractmethod
    async def history(self, execution_id: UUID) -> tuple[ExecutionTransition, ...]: ...

    @abstractmethod
    async def claim_next(self, owner: str, lease_expires_at: datetime) -> Execution | None:
        """Atomically move the oldest QUEUED execution to STARTING under ``owner``'s lease.

        Two workers can never claim the same execution: the claim is a conditional update
        that only one of them can win.
        """

    @abstractmethod
    async def renew_lease(self, execution_id: UUID, owner: str, lease_expires_at: datetime) -> bool:
        """Extend a lease still held by ``owner``; False if it was lost."""

    @abstractmethod
    async def expired_leases(self, now: datetime) -> tuple[Execution, ...]:
        """STARTING/RUNNING executions whose owner stopped renewing (or never had a lease)."""
