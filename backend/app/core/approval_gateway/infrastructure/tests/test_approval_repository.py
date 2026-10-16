"""Durable approval requests: survive restarts, one active per operation, fail closed.

Runs against a freshly migrated SQLite database per test (and PostgreSQL when
GENESIS_TEST_POSTGRES_URL names a disposable database).
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import update

from backend.app.core.approval_gateway.application.approval_service import ApprovalService
from backend.app.core.approval_gateway.domain.approval import (
    Approval,
    ApprovalOutcome,
    ApprovalState,
    DecisionSource,
    OperationBinding,
)
from backend.app.core.approval_gateway.infrastructure.orm import ApprovalRow
from backend.app.core.approval_gateway.infrastructure.sqlalchemy_repository import SqlAlchemyApprovalRepository
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError


def binding(value: object = "x") -> OperationBinding:
    return OperationBinding(
        caller="workflow",
        subject={"workflow_id": "w-1", "workflow_task_id": "step", "workflow_attempt": "1"},
        tool_name="send",
        tool_version="1.0.0",
        tool_contract="c",
        arguments={"to": value, "count": 1},
    )


def fresh(factory) -> ApprovalService:
    """A new service and repository over the same database, as after a restart."""
    return ApprovalService(SqlAlchemyApprovalRepository(factory), EventBus())


@pytest.mark.asyncio
async def test_requests_and_decisions_survive_a_restart(session_factory) -> None:
    first = fresh(session_factory)
    pending = await first.resolve(binding(), reason="side effects")
    await first.approve(pending.approval_id, source=DecisionSource.LOCAL_CONSOLE)

    restarted = fresh(session_factory)
    stored = await restarted.get(pending.approval_id)
    assert stored.state is ApprovalState.APPROVED and stored.decision_source is DecisionSource.LOCAL_CONSOLE
    assert stored.binding == binding() and stored.operation_digest == binding().digest
    assert stored.created_at.tzinfo is not None and stored.expires_at > stored.created_at

    assert await restarted.consume(pending.approval_id, pending.operation_digest) is True
    task_id = uuid4()
    await restarted.record_outcome(pending.approval_id, task_id=task_id, outcome=ApprovalOutcome.COMPLETED)

    again = fresh(session_factory)
    final = await again.get(pending.approval_id)
    assert (final.state, final.task_id, final.outcome) == (ApprovalState.CONSUMED, task_id, ApprovalOutcome.COMPLETED)
    assert await again.consume(pending.approval_id, pending.operation_digest) is False


@pytest.mark.asyncio
async def test_the_database_allows_one_active_request_per_operation(session_factory) -> None:
    repository = SqlAlchemyApprovalRepository(session_factory)
    expires = datetime.now(UTC) + timedelta(hours=1)
    candidates = [Approval(binding=binding(), reason="r", expires_at=expires) for _ in range(5)]

    stored = await asyncio.gather(*(repository.add_or_get_active(candidate) for candidate in candidates))

    assert len({approval.approval_id for approval in stored}) == 1
    assert len(await repository.list(None, 50)) == 1
    # Once it is final, a new request for the same operation can be opened.
    current = stored[0]
    await repository.save(current, current.transition(ApprovalState.REJECTED))
    reopened = await repository.add_or_get_active(Approval(binding=binding(), reason="r", expires_at=expires))
    assert reopened.approval_id != current.approval_id


@pytest.mark.asyncio
async def test_concurrent_consumers_on_the_database_get_one_success(session_factory) -> None:
    approvals = fresh(session_factory)
    pending = await approvals.resolve(binding(), reason="r")
    await approvals.approve(pending.approval_id, source=DecisionSource.LOCAL_CONSOLE)

    consumers = [fresh(session_factory) for _ in range(6)]  # separate services, one database
    results = await asyncio.gather(*(c.consume(pending.approval_id, pending.operation_digest) for c in consumers))

    assert results.count(True) == 1


@pytest.mark.asyncio
async def test_saves_are_compare_and_set(session_factory) -> None:
    repository = SqlAlchemyApprovalRepository(session_factory)
    original = await repository.add_or_get_active(
        Approval(binding=binding(), reason="r", expires_at=datetime.now(UTC) + timedelta(hours=1))
    )
    await repository.save(original, original.transition(ApprovalState.APPROVED))

    with pytest.raises(PersistenceConflictError):
        await repository.save(original, original.transition(ApprovalState.REJECTED))  # stale version
    assert (await repository.get(original.approval_id)).state is ApprovalState.APPROVED


@pytest.mark.asyncio
async def test_corrupt_or_tampered_rows_fail_closed(session_factory) -> None:
    approvals = fresh(session_factory)
    tampered = await approvals.resolve(binding("a"), reason="r")
    corrupt = await approvals.resolve(binding("b"), reason="r")
    healthy = await approvals.resolve(binding("c"), reason="r")
    async with session_factory() as db, db.begin():
        # Someone edits the stored arguments: the digest no longer matches the operation.
        await db.execute(update(ApprovalRow).where(ApprovalRow.id == tampered.approval_id).values(arguments={"to": "attacker", "count": 1}))
    async with session_factory() as db, db.begin():
        await db.execute(update(ApprovalRow).where(ApprovalRow.id == corrupt.approval_id).values(state="approved", subject=["not", "a", "mapping"]))

    for bad in (tampered, corrupt):
        with pytest.raises(PersistenceError):
            await approvals.get(bad.approval_id)
        with pytest.raises(PersistenceError):
            await approvals.consume(bad.approval_id, bad.operation_digest)
    listed = await approvals.list()
    assert [item.approval_id for item in listed] == [healthy.approval_id]  # bad rows are never shown as usable


@pytest.mark.asyncio
async def test_expired_requests_are_marked_when_listed(session_factory) -> None:
    repository = SqlAlchemyApprovalRepository(session_factory)
    old = Approval(binding=binding(), reason="r", expires_at=datetime.now(UTC) - timedelta(seconds=1))
    await repository.add_or_get_active(replace(old, created_at=datetime.now(UTC) - timedelta(hours=2)))
    approvals = ApprovalService(repository, EventBus())

    (listed,) = await approvals.list()

    assert listed.state is ApprovalState.EXPIRED and listed.decision_source is DecisionSource.SYSTEM
