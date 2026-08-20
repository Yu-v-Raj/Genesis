"""Minimal task record that connects an Execution to one Tool invocation."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID, uuid4

from backend.app.core.tool_runtime.domain.tool_result import ToolResult


class TaskStatus(StrEnum):
    """Lifecycle states for a single future-proof unit of work."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    """Immutable task metadata; it is intentionally not a Task Runtime."""

    execution_id: UUID | None
    tool_name: str
    task_id: UUID = field(default_factory=uuid4)
    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    result: ToolResult | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def with_updates(self, **changes: object) -> "Task":
        """Return a copy with lifecycle updates applied."""
        return replace(self, **changes)


def utc_now() -> datetime:
    """Return an aware timestamp for task lifecycle boundaries."""
    return datetime.now(UTC)
