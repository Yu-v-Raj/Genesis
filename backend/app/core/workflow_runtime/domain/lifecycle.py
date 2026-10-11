"""Workflow run and step state machines, and the run retry policy.

Run:
```text
CREATED -> QUEUED -> RUNNING <-> PAUSED
                       |-> COMPLETED                     (final)
                       |-> FAILED      --retry--> QUEUED
                       |-> INTERRUPTED --retry--> QUEUED  (uncertain step; needs a decision)
                       '-> QUEUED                         (recovery: nothing uncertain)
any non-final -> CANCELLED                               (final)
```
Step: PENDING -> READY -> RUNNING -> COMPLETED | FAILED; dependents of a failed step become
BLOCKED; a step running when the process stopped becomes INTERRUPTED unless its tool is
side-effect free, in which case it simply returns to PENDING. A retry resets FAILED,
BLOCKED, CANCELLED, and INTERRUPTED steps to PENDING and never re-runs COMPLETED steps.
"""

from dataclasses import dataclass

from backend.app.core.workflow_runtime.domain.models import WorkflowStatus, WorkflowTaskStatus


FINAL_RUN_STATUSES = frozenset({WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED})
RETRYABLE_RUN_STATUSES = frozenset({WorkflowStatus.FAILED, WorkflowStatus.INTERRUPTED})
FINISHED_RUN_STATUSES = FINAL_RUN_STATUSES | RETRYABLE_RUN_STATUSES

ALLOWED_RUN_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.CREATED: frozenset({WorkflowStatus.QUEUED, WorkflowStatus.CANCELLED}),
    WorkflowStatus.QUEUED: frozenset({WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED}),
    WorkflowStatus.RUNNING: frozenset(
        {
            WorkflowStatus.PAUSED,
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.INTERRUPTED,
            WorkflowStatus.QUEUED,
        }
    ),
    WorkflowStatus.PAUSED: frozenset(
        {WorkflowStatus.RUNNING, WorkflowStatus.QUEUED, WorkflowStatus.CANCELLED, WorkflowStatus.INTERRUPTED}
    ),
    WorkflowStatus.FAILED: frozenset({WorkflowStatus.QUEUED}),
    WorkflowStatus.INTERRUPTED: frozenset({WorkflowStatus.QUEUED, WorkflowStatus.CANCELLED}),
    WorkflowStatus.COMPLETED: frozenset(),
    WorkflowStatus.CANCELLED: frozenset(),
}

RESETTABLE_STEP_STATUSES = frozenset(
    {
        WorkflowTaskStatus.FAILED,
        WorkflowTaskStatus.BLOCKED,
        WorkflowTaskStatus.CANCELLED,
        WorkflowTaskStatus.INTERRUPTED,
    }
)


def can_transition_run(current: WorkflowStatus, target: WorkflowStatus) -> bool:
    return target in ALLOWED_RUN_TRANSITIONS[current]


@dataclass(frozen=True, slots=True)
class RunRetryDecision:
    allowed: bool
    requires_acknowledgement: bool
    reason: str


def run_retry_decision(status: WorkflowStatus, *, uncertain_side_effect_steps: tuple[str, ...]) -> RunRetryDecision:
    if status not in RETRYABLE_RUN_STATUSES:
        return RunRetryDecision(False, False, f"A {status.value} run cannot be retried.")
    if uncertain_side_effect_steps:
        names = ", ".join(uncertain_side_effect_steps)
        return RunRetryDecision(
            True,
            True,
            f"Step(s) {names} were interrupted while running and may already have had external "
            "effects. Retrying runs them again; confirm to retry anyway.",
        )
    return RunRetryDecision(True, False, "Retrying re-runs unfinished steps; completed steps are kept.")
