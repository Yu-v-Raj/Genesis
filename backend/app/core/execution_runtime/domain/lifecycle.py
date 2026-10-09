"""The execution state machine and its retry policy.

```text
PENDING -> QUEUED -> STARTING -> RUNNING -> COMPLETED | FAILED
              ^          |           \\-> INTERRUPTED   (process lost mid-work)
              '----------'  recovery: claimed but never started -> back to QUEUED
any non-terminal -> CANCELLED
```
"""

from dataclasses import dataclass

from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus


TERMINAL_STATUSES = frozenset(
    {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.INTERRUPTED,
    }
)
RETRYABLE_STATUSES = frozenset(
    {ExecutionStatus.FAILED, ExecutionStatus.CANCELLED, ExecutionStatus.INTERRUPTED}
)

ALLOWED_TRANSITIONS: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    ExecutionStatus.PENDING: frozenset({ExecutionStatus.QUEUED, ExecutionStatus.CANCELLED}),
    ExecutionStatus.QUEUED: frozenset({ExecutionStatus.STARTING, ExecutionStatus.CANCELLED}),
    # STARTING -> QUEUED is recovery of claimed-but-never-started work.
    ExecutionStatus.STARTING: frozenset(
        {ExecutionStatus.RUNNING, ExecutionStatus.QUEUED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
    ),
    ExecutionStatus.RUNNING: frozenset(
        {
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.INTERRUPTED,
        }
    ),
    **{status: frozenset() for status in TERMINAL_STATUSES},
}


def can_transition(current: ExecutionStatus, target: ExecutionStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Whether a finished execution may be retried, and whether that needs confirmation."""

    allowed: bool
    requires_acknowledgement: bool
    reason: str


def retry_decision(status: ExecutionStatus, *, may_have_side_effects: bool) -> RetryDecision:
    if status not in RETRYABLE_STATUSES:
        return RetryDecision(False, False, f"A {status.value} execution cannot be retried.")
    if status is ExecutionStatus.INTERRUPTED and may_have_side_effects:
        return RetryDecision(
            True,
            True,
            "This work was interrupted after it started and may already have had external "
            "effects. Retrying could repeat them; confirm to retry anyway.",
        )
    return RetryDecision(True, False, "Retrying starts a new attempt with the same input.")
