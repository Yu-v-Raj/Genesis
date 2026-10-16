"""Approval lifecycle, exact-operation binding and single use (Milestone 2).

Runs the real ApprovalService against the in-memory repository; the SQLAlchemy adapter
has its own contract tests under infrastructure/tests.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.core.approval_gateway.application.approval_service import ApprovalService
from backend.app.core.approval_gateway.application.in_memory_repository import InMemoryApprovalRepository
from backend.app.core.approval_gateway.domain.approval import (
    REDACTED,
    Approval,
    ApprovalError,
    ApprovalNotFoundError,
    ApprovalOutcome,
    ApprovalState,
    ApprovalTransitionError,
    DecisionSource,
    OperationBinding,
    canonical_json,
    redact_arguments,
)
from backend.app.core.core_services.event_bus import EventBus


LOCAL = DecisionSource.LOCAL_CONSOLE


def binding(**overrides: object) -> OperationBinding:
    values: dict[str, object] = {
        "caller": "agent",
        "subject": {"agent_id": "a-1", "execution_id": "e-1"},
        "tool_name": "send",
        "tool_version": "1.0.0",
        "tool_contract": "contract-1",
        "arguments": {"to": "x", "count": 1},
    }
    values.update(overrides)
    return OperationBinding(**values)  # type: ignore[arg-type]


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def service(clock: Clock | None = None, ttl: float = 60) -> tuple[ApprovalService, list]:
    bus = EventBus()
    events: list = []
    bus.subscribe(events.append)
    return ApprovalService(InMemoryApprovalRepository(), bus, ttl_seconds=ttl, clock=clock or Clock()), events


# ------------------------------------------------------------------- binding


def test_the_digest_covers_every_part_of_the_operation() -> None:
    base = binding()
    variants = [
        binding(arguments={"to": "x", "count": 1.0}),  # 1 and 1.0 are different values
        binding(arguments={"to": "x", "count": True}),
        binding(arguments={"to": "y", "count": 1}),
        binding(caller="operator"),
        binding(subject={"agent_id": "a-2", "execution_id": "e-1"}),
        binding(subject={"agent_id": "a-1", "execution_id": "e-2"}),
        binding(tool_name="send2"),
        binding(tool_version="2.0.0"),
        binding(tool_contract="contract-2"),
    ]
    assert len({base.digest, *(variant.digest for variant in variants)}) == len(variants) + 1
    assert binding(arguments={"count": 1, "to": "x"}).digest == base.digest  # key order is irrelevant


def test_canonical_json_rejects_values_that_are_not_plain_json() -> None:
    for value in ({"x": float("nan")}, {"x": float("inf")}, {"x": object()}, {1: "x"}):
        with pytest.raises(ValueError):
            canonical_json(value)
    assert canonical_json({"b": [1, 1.0, True], "a": None}) == '{"a":null,"b":[1,1.0,true]}'


def test_a_stored_record_whose_operation_was_altered_is_refused() -> None:
    original = Approval(binding=binding(), reason="r", expires_at=datetime.now(UTC))
    with pytest.raises(ValueError, match="no longer matches"):
        Approval(binding=binding(arguments={"to": "attacker"}), reason="r", expires_at=original.expires_at, operation_digest=original.operation_digest)


def test_redaction_hides_secret_looking_fields_and_says_which() -> None:
    shown, redacted = redact_arguments(
        {"to": "bob", "api_key": "abc", "nested": {"Password": "p", "note": "sk-abcdefghijklmnopqrstu"}, "items": [{"token": "t"}], "empty_token": ""}
    )
    assert shown == {"to": "bob", "api_key": REDACTED, "nested": {"Password": REDACTED, "note": REDACTED}, "items": [{"token": REDACTED}], "empty_token": ""}
    assert set(redacted) == {"api_key", "nested.Password", "nested.note", "items[0].token"}


# ----------------------------------------------------------------- lifecycle


@pytest.mark.parametrize(
    ("start", "target", "allowed"),
    [
        (ApprovalState.PENDING, ApprovalState.APPROVED, True),
        (ApprovalState.PENDING, ApprovalState.REJECTED, True),
        (ApprovalState.PENDING, ApprovalState.CONSUMED, False),  # never consumed without approval
        (ApprovalState.APPROVED, ApprovalState.CONSUMED, True),
        (ApprovalState.APPROVED, ApprovalState.REJECTED, False),
        (ApprovalState.APPROVED, ApprovalState.APPROVED, False),
        (ApprovalState.CONSUMED, ApprovalState.CONSUMED, False),  # single use
        (ApprovalState.CONSUMED, ApprovalState.CANCELLED, False),
        (ApprovalState.REJECTED, ApprovalState.APPROVED, False),
        (ApprovalState.EXPIRED, ApprovalState.APPROVED, False),
        (ApprovalState.CANCELLED, ApprovalState.APPROVED, False),
    ],
)
def test_transitions(start: ApprovalState, target: ApprovalState, allowed: bool) -> None:
    approval = Approval(binding=binding(), reason="r", expires_at=datetime.now(UTC), state=start)
    if allowed:
        assert approval.transition(target).state is target
    else:
        with pytest.raises(ApprovalTransitionError):
            approval.transition(target)


@pytest.mark.asyncio
async def test_resolve_opens_one_pending_request_per_operation_and_publishes_no_arguments() -> None:
    approvals, events = service()
    first = await approvals.resolve(binding(), reason="side effects")
    again = await approvals.resolve(binding(), reason="side effects")
    other = await approvals.resolve(binding(arguments={"to": "y", "count": 1}), reason="side effects")

    assert first.state is ApprovalState.PENDING and again.approval_id == first.approval_id
    assert other.approval_id != first.approval_id
    requested = [event for event in events if event.event_type == "approval.requested"]
    assert len(requested) == 2
    assert all("arguments" not in event.payload and "x" not in event.payload.values() for event in requested)
    assert requested[0].payload["agent_id"] == "a-1" and requested[0].payload["tool_name"] == "send"


@pytest.mark.asyncio
async def test_approve_then_consume_exactly_once() -> None:
    approvals, events = service()
    pending = await approvals.resolve(binding(), reason="r")
    assert await approvals.consume(pending.approval_id, pending.operation_digest) is False  # not approved yet

    approved = await approvals.approve(pending.approval_id, source=LOCAL)
    assert approved.state is ApprovalState.APPROVED and approved.decision_source is LOCAL and approved.decided_at is not None
    assert (await approvals.resolve(binding(), reason="r")).state is ApprovalState.APPROVED  # same request stands
    assert await approvals.consume(pending.approval_id, "another-digest") is False
    assert await approvals.consume(pending.approval_id, pending.operation_digest) is True
    assert await approvals.consume(pending.approval_id, pending.operation_digest) is False

    task_id = uuid4()
    await approvals.record_outcome(pending.approval_id, task_id=task_id, outcome=ApprovalOutcome.FAILED, detail="tool failed")
    await approvals.record_outcome(pending.approval_id, task_id=uuid4(), outcome=ApprovalOutcome.COMPLETED)  # ignored
    stored = await approvals.get(pending.approval_id)
    assert stored.state is ApprovalState.CONSUMED and stored.task_id == task_id and stored.outcome is ApprovalOutcome.FAILED
    # A consumed approval is not active: the same operation needs a new request.
    assert (await approvals.resolve(binding(), reason="r")).approval_id != pending.approval_id
    assert [e.event_type for e in events if e.event_type.startswith("approval.") and e.event_type != "approval.requested"] == [
        "approval.approved", "approval.consumed", "approval.outcome",
    ]


@pytest.mark.asyncio
async def test_concurrent_consumers_get_one_success() -> None:
    approvals, _ = service()
    pending = await approvals.resolve(binding(), reason="r")
    await approvals.approve(pending.approval_id, source=LOCAL)

    results = await asyncio.gather(*(approvals.consume(pending.approval_id, pending.operation_digest) for _ in range(10)))

    assert results.count(True) == 1


@pytest.mark.asyncio
async def test_decisions_are_final_and_races_report_the_winner() -> None:
    approvals, _ = service()
    pending = await approvals.resolve(binding(), reason="r")

    results = await asyncio.gather(
        approvals.approve(pending.approval_id, source=LOCAL),
        approvals.reject(pending.approval_id, source=LOCAL),
        approvals.approve(pending.approval_id, source=LOCAL),
        return_exceptions=True,
    )
    winners = [result for result in results if isinstance(result, Approval)]
    losers = [result for result in results if isinstance(result, ApprovalTransitionError)]
    assert len(winners) == 1 and len(losers) == 2
    final = await approvals.get(pending.approval_id)
    assert final.state is winners[0].state
    with pytest.raises(ApprovalTransitionError):
        await approvals.approve(pending.approval_id, source=LOCAL)


@pytest.mark.asyncio
async def test_rejection_is_recorded_and_never_consumable() -> None:
    approvals, _ = service()
    pending = await approvals.resolve(binding(), reason="r")
    rejected = await approvals.reject(pending.approval_id, source=DecisionSource.LOCAL_API)

    assert rejected.state is ApprovalState.REJECTED and rejected.decision_source is DecisionSource.LOCAL_API
    assert await approvals.consume(pending.approval_id, pending.operation_digest) is False
    with pytest.raises(ApprovalTransitionError, match="rejected"):
        await approvals.approve(pending.approval_id, source=LOCAL)


@pytest.mark.asyncio
async def test_expiry_applies_to_pending_and_unused_approvals() -> None:
    clock = Clock()
    approvals, events = service(clock, ttl=60)
    pending = await approvals.resolve(binding(), reason="r")
    approved = await approvals.resolve(binding(arguments={"to": "z", "count": 1}), reason="r")
    await approvals.approve(approved.approval_id, source=LOCAL)

    clock.now += timedelta(seconds=59)
    assert await approvals.state_of(pending.approval_id) is ApprovalState.PENDING
    clock.now += timedelta(seconds=1)  # the deadline itself counts as expired

    with pytest.raises(ApprovalTransitionError, match="expired"):
        await approvals.approve(pending.approval_id, source=LOCAL)
    assert await approvals.consume(approved.approval_id, approved.operation_digest) is False
    assert await approvals.state_of(approved.approval_id) is ApprovalState.EXPIRED
    assert (await approvals.get(approved.approval_id)).detail == "The approved operation did not run before the approval expired."
    assert (await approvals.resolve(binding(), reason="r")).approval_id != pending.approval_id
    assert "approval.expired" in [event.event_type for event in events]


@pytest.mark.asyncio
async def test_cancel_only_affects_active_requests_and_notifies_listeners() -> None:
    approvals, _ = service()
    notified: list[ApprovalState] = []
    approvals.add_listener(lambda approval: notified.append(approval.state))
    pending = await approvals.resolve(binding(), reason="r")

    cancelled = await approvals.cancel(pending.approval_id, reason="The run was cancelled.")
    again = await approvals.cancel(pending.approval_id, reason="again")

    assert cancelled is not None and cancelled.state is ApprovalState.CANCELLED and cancelled.detail == "The run was cancelled."
    assert again is not None and again.detail == "The run was cancelled."  # unchanged
    assert notified == [ApprovalState.CANCELLED]
    assert await approvals.consume(pending.approval_id, pending.operation_digest) is False


@pytest.mark.asyncio
async def test_a_failing_listener_does_not_undo_a_decision() -> None:
    approvals, _ = service()

    def broken(_: Approval) -> None:
        raise RuntimeError("listener bug")

    approvals.add_listener(broken)
    pending = await approvals.resolve(binding(), reason="r")
    await approvals.approve(pending.approval_id, source=LOCAL)

    assert await approvals.state_of(pending.approval_id) is ApprovalState.APPROVED


@pytest.mark.asyncio
async def test_unknown_requests() -> None:
    approvals, _ = service()
    missing = uuid4()
    with pytest.raises(ApprovalNotFoundError):
        await approvals.approve(missing, source=LOCAL)
    assert await approvals.state_of(missing) is None
    assert await approvals.consume(missing, "d") is False
    assert await approvals.cancel(missing, reason="r") is None


def test_an_outcome_is_recorded_only_after_consumption() -> None:
    approval = Approval(binding=binding(), reason="r", expires_at=datetime.now(UTC), state=ApprovalState.APPROVED)
    with pytest.raises(ApprovalError):
        approval.transition_outcome(task_id=None, outcome=ApprovalOutcome.COMPLETED, detail=None)
