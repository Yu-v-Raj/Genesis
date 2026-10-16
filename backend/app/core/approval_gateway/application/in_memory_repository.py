"""Process-local approval repository with the same contract as the database adapter.

Used by focused tests; the application always uses the SQLAlchemy repository.
"""

import asyncio
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from backend.app.core.approval_gateway.application.repositories import ApprovalRepository
from backend.app.core.approval_gateway.domain.approval import ACTIVE_STATES, Approval, ApprovalState
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError


class InMemoryApprovalRepository(ApprovalRepository):
    def __init__(self) -> None:
        self._items: dict[UUID, Approval] = {}
        self._lock = asyncio.Lock()

    async def add_or_get_active(self, approval: Approval) -> Approval:
        async with self._lock:
            existing = self._active(approval.operation_digest)
            if existing is not None:
                return existing
            self._items[approval.approval_id] = approval
            return approval

    async def get(self, approval_id: UUID) -> Approval | None:
        return self._items.get(approval_id)

    async def active_for(self, operation_digest: str) -> Approval | None:
        return self._active(operation_digest)

    async def save(self, current: Approval, updated: Approval) -> Approval:
        async with self._lock:
            stored = self._items.get(current.approval_id)
            if stored is None:
                raise PersistenceError("The approval request no longer exists in storage.")
            if stored.version != current.version:
                raise PersistenceConflictError("The approval request changed concurrently.")
            saved = replace(updated, version=current.version + 1)
            self._items[saved.approval_id] = saved
            return saved

    async def list(self, states: frozenset[ApprovalState] | None, limit: int) -> tuple[Approval, ...]:
        items = sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)
        return tuple(item for item in items if states is None or item.state in states)[:limit]

    async def due_for_expiry(self, now: datetime) -> tuple[Approval, ...]:
        return tuple(item for item in self._items.values() if item.state in ACTIVE_STATES and item.expires_at <= now)

    def _active(self, digest: str) -> Approval | None:
        return next((item for item in self._items.values() if item.operation_digest == digest and item.state in ACTIVE_STATES), None)
