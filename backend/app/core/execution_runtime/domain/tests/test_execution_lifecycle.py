"""The execution state machine and retry policy."""

import pytest

from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus as S
from backend.app.core.execution_runtime.domain.lifecycle import (
    TERMINAL_STATUSES,
    can_transition,
    retry_decision,
)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.PENDING, S.QUEUED),
        (S.QUEUED, S.STARTING),
        (S.STARTING, S.RUNNING),
        (S.STARTING, S.QUEUED),  # recovery: claimed but never started
        (S.RUNNING, S.COMPLETED),
        (S.RUNNING, S.FAILED),
        (S.RUNNING, S.INTERRUPTED),
        (S.QUEUED, S.CANCELLED),
        (S.RUNNING, S.CANCELLED),
    ],
)
def test_valid_transitions(current: S, target: S) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.QUEUED, S.RUNNING),  # must be claimed first
        (S.RUNNING, S.QUEUED),  # work may have begun: never silently re-queued
        (S.QUEUED, S.INTERRUPTED),  # nothing started, nothing to be uncertain about
        (S.PENDING, S.COMPLETED),
    ],
)
def test_invalid_transitions(current: S, target: S) -> None:
    assert not can_transition(current, target)


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATUSES))
def test_terminal_states_never_change(terminal: S) -> None:
    assert not any(can_transition(terminal, target) for target in S)


def test_retry_policy() -> None:
    assert not retry_decision(S.COMPLETED, may_have_side_effects=False).allowed
    assert not retry_decision(S.RUNNING, may_have_side_effects=False).allowed
    failed = retry_decision(S.FAILED, may_have_side_effects=True)
    assert failed.allowed and not failed.requires_acknowledgement
    safe = retry_decision(S.INTERRUPTED, may_have_side_effects=False)
    assert safe.allowed and not safe.requires_acknowledgement
    risky = retry_decision(S.INTERRUPTED, may_have_side_effects=True)
    assert risky.allowed and risky.requires_acknowledgement
    assert "external effects" in risky.reason
