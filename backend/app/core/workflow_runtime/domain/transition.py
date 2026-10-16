"""Durable timeline entries for workflow runs and their steps."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from backend.app.core.workflow_runtime.domain.models import Workflow, utc_now


MAX_TRANSITION_DETAIL = 1_000


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowTransition:
    """One recorded status change of a run (``step_id`` None) or of one of its steps.

    Stored in the same transaction as the change itself, so the timeline always matches
    the run. ``worker`` is the lease owner after the change, when there is one.
    """

    run_id: UUID
    sequence: int
    step_id: str | None
    attempt: int
    from_status: str | None
    to_status: str
    at: datetime
    worker: str | None = None
    detail: str | None = None


def transitions_between(current: Workflow | None, updated: Workflow, *, first_sequence: int) -> tuple[WorkflowTransition, ...]:
    """The status changes from ``current`` (None for a new run) to ``updated``: the run's
    own change first, then each step's in definition order."""
    at = utc_now()
    entries: list[WorkflowTransition] = []

    def add(step_id: str | None, before: str | None, after: str, detail: str | None) -> None:
        entries.append(
            WorkflowTransition(
                run_id=updated.workflow_id,
                sequence=first_sequence + len(entries),
                step_id=step_id,
                attempt=updated.attempt,
                from_status=before,
                to_status=after,
                at=at,
                worker=updated.lease_owner,
                detail=None if detail is None else detail[:MAX_TRANSITION_DETAIL],
            )
        )

    if current is None or current.status is not updated.status or current.attempt != updated.attempt:
        add(None, None if current is None else current.status.value, updated.status.value, updated.error)
    before = {} if current is None else {task.task_id: task for task in current.tasks}
    for task in updated.tasks:
        previous = before.get(task.task_id)
        if current is not None and (previous is None or previous.status is not task.status):
            add(task.task_id, None if previous is None else previous.status.value, task.status.value, task.error)
    return tuple(entries)
