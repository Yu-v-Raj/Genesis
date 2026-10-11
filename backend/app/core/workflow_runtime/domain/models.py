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
    """State of one workflow run. INTERRUPTED: the process stopped while a step with possible
    side effects was running, so a person must decide whether to retry it."""
    CREATED = "created"; QUEUED = "queued"; RUNNING = "running"; PAUSED = "paused"; COMPLETED = "completed"; FAILED = "failed"; CANCELLED = "cancelled"; INTERRUPTED = "interrupted"


class WorkflowTaskStatus(StrEnum):
    """State of one step in a run. INTERRUPTED: it was running when the process stopped and
    its outcome is unknown."""
    PENDING = "pending"; READY = "ready"; RUNNING = "running"; COMPLETED = "completed"; FAILED = "failed"; CANCELLED = "cancelled"; BLOCKED = "blocked"; INTERRUPTED = "interrupted"


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
    """One run of a workflow definition: a snapshot of its steps plus their progress."""
    workflow_id: UUID = field(default_factory=uuid4)
    name: str
    description: str = ""
    tasks: tuple[WorkflowTask, ...] = ()
    status: WorkflowStatus = WorkflowStatus.CREATED
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, object] = field(default_factory=dict)
    # Durability (v0.12)
    definition_id: UUID | None = None
    definition_version: int | None = None
    attempt: int = 1
    error: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    version: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip(): raise ValueError("Workflow names must be non-empty strings.")
        if not self.tasks: raise ValueError("A workflow must contain at least one task.")
        object.__setattr__(self, "tasks", tuple(self.tasks))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def with_updates(self, **changes: object) -> "Workflow":
        return replace(self, updated_at=utc_now(), **changes)

    def with_task(self, updated: WorkflowTask) -> "Workflow":
        return self.with_updates(tasks=tuple(updated if task.task_id == updated.task_id else task for task in self.tasks))


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowDefinition:
    """A reusable, versioned plan. Each version is immutable; runs snapshot one version, so
    editing a definition never changes a run that already exists."""
    definition_id: UUID = field(default_factory=uuid4)
    version: int = 1
    name: str
    description: str = ""
    tasks: tuple[WorkflowTask, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip(): raise ValueError("Workflow names must be non-empty strings.")
        if not self.tasks: raise ValueError("A workflow must contain at least one task.")
        if self.version < 1: raise ValueError("Workflow definition versions start at 1.")
        object.__setattr__(self, "tasks", tuple(task.with_updates(workflow_id=None, status=WorkflowTaskStatus.PENDING) for task in self.tasks))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def new_run(self) -> Workflow:
        """Create a run whose steps are a frozen copy of this version."""
        run_id = uuid4()
        return Workflow(
            workflow_id=run_id,
            name=self.name,
            description=self.description,
            metadata=self.metadata,
            definition_id=self.definition_id,
            definition_version=self.version,
            tasks=tuple(task.with_updates(workflow_id=run_id, created_at=utc_now()) for task in self.tasks),
        )
