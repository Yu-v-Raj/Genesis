"""Persistence port for tool tasks (one record per tool invocation).

The record is written before the tool runs and again at every state change, so history
survives a restart and a task never silently disappears while running. Tasks found
unfinished at startup are closed as interrupted: their external effect is unknown.
"""

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from threading import RLock
from uuid import UUID

from backend.app.core.core_services.pagination import PageCursor, comes_after, newest_first
from backend.app.core.tool_runtime.domain.task import Task, TaskStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskQuery:
    """Exact-match filters; every one comes from the task's trusted metadata."""

    execution_id: UUID | None = None
    workflow_id: UUID | None = None
    approval_id: UUID | None = None
    tool_name: str | None = None


class ToolTaskRepository(ABC):
    @abstractmethod
    async def save(self, task: Task) -> None:
        """Insert or replace the task's current snapshot."""

    @abstractmethod
    async def get(self, task_id: UUID) -> Task | None: ...

    @abstractmethod
    async def page(self, query: TaskQuery, *, before: PageCursor | None, limit: int) -> tuple[Task, ...]:
        """Newest first by (created_at, task_id), strictly after the ``before`` cursor when given."""

    @abstractmethod
    async def unfinished(self) -> tuple[Task, ...]:
        """Tasks still pending or running in storage."""


def matches(task: Task, query: TaskQuery) -> bool:
    meta = task.metadata
    return (
        (query.execution_id is None or task.execution_id == query.execution_id)
        and (query.workflow_id is None or meta.get("workflow_id") == str(query.workflow_id))
        and (query.approval_id is None or meta.get("approval_id") == str(query.approval_id))
        and (query.tool_name is None or task.tool_name == query.tool_name)
    )


class InMemoryToolTaskRepository(ToolTaskRepository):
    """Bounded process-local store (tests, and when no database is configured)."""

    def __init__(self, capacity: int = 1000) -> None:
        self._tasks: dict[UUID, Task] = {}
        self._order: deque[UUID] = deque()
        self._capacity = capacity
        self._lock = RLock()

    async def save(self, task: Task) -> None:
        with self._lock:
            if task.task_id not in self._tasks:
                self._order.append(task.task_id)
            self._tasks[task.task_id] = task
            while len(self._order) > self._capacity:
                self._tasks.pop(self._order.popleft(), None)

    async def get(self, task_id: UUID) -> Task | None:
        return self._tasks.get(task_id)

    async def page(self, query: TaskQuery, *, before: PageCursor | None, limit: int) -> tuple[Task, ...]:
        with self._lock:
            tasks = newest_first(self._tasks.values(), lambda task: task.created_at, lambda task: task.task_id)
        return tuple(t for t in tasks if comes_after(t.created_at, t.task_id, before) and matches(t, query))[:limit]

    async def unfinished(self) -> tuple[Task, ...]:
        return tuple(t for t in self._tasks.values() if t.status in {TaskStatus.PENDING, TaskStatus.RUNNING})
