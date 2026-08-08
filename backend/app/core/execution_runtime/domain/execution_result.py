"""Outcome data produced by an execution."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionResult:
    """Immutable result emitted when an execution reaches a terminal state."""

    status: ExecutionStatus
    output: str | None = None
    duration: float | None = None
    logs: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze mutable values at the execution domain boundary."""
        if self.status not in {ExecutionStatus.COMPLETED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}:
            raise ValueError("Execution result status must be terminal.")
        if self.duration is not None and self.duration < 0:
            raise ValueError("Execution result duration cannot be negative.")
        object.__setattr__(self, "logs", tuple(self.logs))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
