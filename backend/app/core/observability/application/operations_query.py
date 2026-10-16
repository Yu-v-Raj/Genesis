"""Read model for Operations: assemble the trace of one execution or workflow run.

Pure reads across the runtimes' own services. Nothing here changes state: no lease is
renewed, no approval is expired, no event is written. Each runtime keeps its own records
(executions, workflow runs, tool tasks, approvals, runtime events); a trace joins them by
the identifiers each record carries from its trusted execution context.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from backend.app.core.approval_gateway.domain.approval import Approval
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.transition import ExecutionTransition
from backend.app.core.observability.application.runtime_event_store import RuntimeEventStore
from backend.app.core.observability.domain.runtime_event import EventQuery, StoredEvent
from backend.app.core.tool_runtime.application.task_repository import TaskQuery
from backend.app.core.tool_runtime.domain.task import Task
from backend.app.core.workflow_runtime.domain.models import Workflow
from backend.app.core.workflow_runtime.domain.transition import WorkflowTransition


TRACE_TOOL_TASK_LIMIT = 200
TRACE_APPROVAL_LIMIT = 200
TRACE_EVENT_LIMIT = 500


class _Executions(Protocol):
    async def get_execution(self, execution_id: UUID) -> Execution: ...
    async def execution_history(self, execution_id: UUID) -> tuple[ExecutionTransition, ...]: ...


class _Workflows(Protocol):
    async def get(self, workflow_id: UUID) -> Workflow: ...
    async def transitions(self, workflow_id: UUID) -> tuple[WorkflowTransition, ...]: ...


class _Tools(Protocol):
    async def task_page(self, query: TaskQuery, *, before: object = None, limit: int = 50) -> tuple[Task, ...]: ...


class _Approvals(Protocol):
    async def related(self, *, execution_id: UUID | None = None, workflow_id: UUID | None = None, limit: int = 200) -> tuple[Approval, ...]: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class TracePart:
    """Records related to one trace, oldest first; ``truncated`` when a limit cut it."""

    tool_tasks: tuple[Task, ...]
    approvals: tuple[Approval, ...]
    events: tuple[StoredEvent, ...]
    tool_tasks_truncated: bool
    approvals_truncated: bool
    events_truncated: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionTrace:
    execution: Execution
    transitions: tuple[ExecutionTransition, ...]
    related: TracePart


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowTrace:
    run: Workflow
    transitions: tuple[WorkflowTransition, ...]
    related: TracePart


@dataclass(frozen=True, slots=True, kw_only=True)
class EventPage:
    events: tuple[StoredEvent, ...]  # newest first
    next_before_sequence: int | None


class OperationsQueryService:
    def __init__(
        self, *, executions: _Executions, workflows: _Workflows, tools: _Tools, approvals: _Approvals, events: RuntimeEventStore
    ) -> None:
        self._executions = executions
        self._workflows = workflows
        self._tools = tools
        self._approvals = approvals
        self._events = events

    async def execution_trace(self, execution_id: UUID) -> ExecutionTrace:
        """Raises ExecutionNotFoundError for an unknown execution."""
        execution = await self._executions.get_execution(execution_id)
        return ExecutionTrace(
            execution=execution,
            transitions=await self._executions.execution_history(execution_id),
            related=await self._related(TaskQuery(execution_id=execution_id), EventQuery(execution_id=execution_id), execution_id=execution_id),
        )

    async def workflow_trace(self, workflow_id: UUID) -> WorkflowTrace:
        """Raises WorkflowNotFoundError for an unknown run."""
        run = await self._workflows.get(workflow_id)
        return WorkflowTrace(
            run=run,
            transitions=await self._workflows.transitions(workflow_id),
            related=await self._related(TaskQuery(workflow_id=workflow_id), EventQuery(workflow_id=workflow_id), workflow_id=workflow_id),
        )

    async def events(self, query: EventQuery, *, before_sequence: int | None = None, limit: int = 100) -> EventPage:
        page = await self._events.page(query, before_sequence=before_sequence, limit=limit + 1)
        more = len(page) > limit
        page = page[:limit]
        return EventPage(events=page, next_before_sequence=page[-1].sequence if more and page else None)

    async def _related(
        self, tasks: TaskQuery, events: EventQuery, *, execution_id: UUID | None = None, workflow_id: UUID | None = None
    ) -> TracePart:
        # One extra row of each tells whether the limit cut the list.
        found_tasks = await self._tools.task_page(tasks, limit=TRACE_TOOL_TASK_LIMIT + 1)
        found_approvals = await self._approvals.related(execution_id=execution_id, workflow_id=workflow_id, limit=TRACE_APPROVAL_LIMIT + 1)
        found_events = await self._events.page(events, before_sequence=None, limit=TRACE_EVENT_LIMIT + 1)
        return TracePart(
            tool_tasks=tuple(reversed(found_tasks[:TRACE_TOOL_TASK_LIMIT])),
            approvals=tuple(reversed(found_approvals[:TRACE_APPROVAL_LIMIT])),
            events=tuple(reversed(found_events[:TRACE_EVENT_LIMIT])),
            tool_tasks_truncated=len(found_tasks) > TRACE_TOOL_TASK_LIMIT,
            approvals_truncated=len(found_approvals) > TRACE_APPROVAL_LIMIT,
            events_truncated=len(found_events) > TRACE_EVENT_LIMIT,
        )
