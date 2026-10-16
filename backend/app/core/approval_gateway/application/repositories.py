"""Persistence port for approval requests.

Every change is compare-and-set on ``Approval.version``, so two concurrent decisions or
two concurrent consumers can never both succeed: the loser gets
``PersistenceConflictError`` and re-reads the stored state.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from backend.app.core.approval_gateway.domain.approval import Approval, ApprovalState


class ApprovalRepository(ABC):
    @abstractmethod
    async def add_or_get_active(self, approval: Approval) -> Approval:
        """Store a new PENDING request, unless an active (pending or approved) request for
        the same operation digest exists: then return that one instead. At most one active
        request per digest, even under concurrent calls."""

    @abstractmethod
    async def get(self, approval_id: UUID) -> Approval | None: ...

    @abstractmethod
    async def active_for(self, operation_digest: str) -> Approval | None: ...

    @abstractmethod
    async def save(self, current: Approval, updated: Approval) -> Approval:
        """Replace ``current`` with ``updated`` if nobody changed it meanwhile; returns the
        stored record (version incremented). Raises PersistenceConflictError otherwise."""

    @abstractmethod
    async def list(self, states: frozenset[ApprovalState] | None, limit: int) -> tuple[Approval, ...]:
        """Newest first."""

    @abstractmethod
    async def related(self, *, execution_id: UUID | None = None, workflow_id: UUID | None = None, limit: int = 200) -> tuple[Approval, ...]:
        """Requests made for one execution or one workflow run, newest first. Read only."""

    @abstractmethod
    async def due_for_expiry(self, now: datetime) -> tuple[Approval, ...]:
        """Active requests whose deadline has passed."""
