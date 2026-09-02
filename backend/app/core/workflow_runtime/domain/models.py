"""Immutable records and explicit state machines for workflow coordination."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID, uuid4


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkflowStatus(StrEnum):
    CREATED = "created"; QUEUED = "queued"; RUNNING = "running"; PAUSED = "paused"; COMPLETED = "completed"; FAILED = "failed"; CANCELLED = "cancelled"


class WorkflowTaskStatus(StrEnum):
    PENDING = "pending"; READY = "ready"; RUNNING = "running"; COMPLETED = "completed"; FAILED = "failed"; CANCELLED = "cancelled"; BLOCKED = "blocked"


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowTask:
    """A requested workflow step, distinct from a Tool Runtime execution task."""
    task_id: str
    name: str
    workflow_id: UUID | None = None
    action: str = "tool"
    configuration: Mapping[str, object] = field(default_factory=dict)
    dependencies: tuple[str, ...] = ()
    status: WorkflowTaskStatus = WorkflowTaskStatus.PENDING
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: object | None = None
    error: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip(): raise ValueError("Workflow task IDs must be non-empty strings.")
        if not isinstance(self.name, str) or not self.name.strip(): raise ValueError("Workflow task names must be non-empty strings.")
        if self.action != "tool": raise ValueError("Only tool workflow tasks are supported.")
        object.__setattr__(self, "configuration", MappingProxyType(dict(self.configuration)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(self, "dependencies", tuple(self.dependencies))

    def with_updates(self, **changes: object) -> "WorkflowTask":
        return replace(self, **changes)


@dataclass(frozen=True, slots=True, kw_only=True)
class Workflow:
    workflow_id: UUID = field(default_factory=uuid4)
    name: str
    description: str = ""
    tasks: tuple[WorkflowTask, ...] = ()
    status: WorkflowStatus = WorkflowStatus.CREATED
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip(): raise ValueError("Workflow names must be non-empty strings.")
        if not self.tasks: raise ValueError("A workflow must contain at least one task.")
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def with_updates(self, **changes: object) -> "Workflow":
        return replace(self, updated_at=utc_now(), **changes)

    def with_task(self, updated: WorkflowTask) -> "Workflow":
        return self.with_updates(tasks=tuple(updated if task.task_id == updated.task_id else task for task in self.tasks))
