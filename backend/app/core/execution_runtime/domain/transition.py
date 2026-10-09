"""Durable timeline entries for an execution."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionTransition:
    """One recorded state change, stored in the same transaction as the change itself."""

    execution_id: UUID
    sequence: int
    from_status: ExecutionStatus | None
    to_status: ExecutionStatus
    at: datetime
    detail: str | None = None
