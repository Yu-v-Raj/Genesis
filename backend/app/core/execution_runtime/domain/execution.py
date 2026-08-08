"""Immutable metadata for one Agent execution."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping
from uuid import UUID, uuid4

from backend.app.core.execution_runtime.domain.execution_result import ExecutionResult
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class Execution:
    """Persistent execution metadata; mutable runtime state belongs in ExecutionContext."""

    agent_id: UUID
    execution_id: UUID = field(default_factory=uuid4)
    status: ExecutionStatus = ExecutionStatus.PENDING
    created_at: datetime = field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: ExecutionResult | None = None
    error: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate timestamps and make metadata safely immutable."""
        if not isinstance(self.status, ExecutionStatus):
            raise TypeError("Execution status must be an ExecutionStatus value.")
        if self.created_at.tzinfo is None:
            raise ValueError("Execution created_at must be timezone-aware.")
        if self.started_at is not None and self.started_at.tzinfo is None:
            raise ValueError("Execution started_at must be timezone-aware.")
        if self.finished_at is not None and self.finished_at.tzinfo is None:
            raise ValueError("Execution finished_at must be timezone-aware.")
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("Execution started_at cannot precede created_at.")
        if self.finished_at is not None and self.finished_at < self.created_at:
            raise ValueError("Execution finished_at cannot precede created_at.")
        if self.result is not None and self.result.status is not self.status:
            raise ValueError("Execution result status must match execution status.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def duration(self) -> float | None:
        """Return elapsed seconds for a started execution."""
        if self.started_at is None:
            return None
        end = self.finished_at or _utc_now()
        return max(0.0, (end - self.started_at).total_seconds())

    def with_status(self, status: ExecutionStatus, **changes: object) -> "Execution":
        """Return a copy with the supplied lifecycle fields changed."""
        return replace(self, status=status, **changes)
