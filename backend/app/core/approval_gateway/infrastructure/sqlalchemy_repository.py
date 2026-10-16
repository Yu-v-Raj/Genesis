"""SQLAlchemy adapter for the approval repository port."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.approval_gateway.application.repositories import ApprovalRepository
from backend.app.core.approval_gateway.domain.approval import (
    ACTIVE_STATES,
    Approval,
    ApprovalOutcome,
    ApprovalState,
    DecisionSource,
    OperationBinding,
)
from backend.app.core.approval_gateway.infrastructure.orm import ApprovalRow
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.database.transactions import persistence_transaction


_ACTIVE = tuple(state.value for state in ACTIVE_STATES)


class SqlAlchemyApprovalRepository(ApprovalRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def add_or_get_active(self, approval: Approval) -> Approval:
        try:
            async with persistence_transaction(self._factory, "approval.add") as db:
                await db.execute(insert(ApprovalRow).values(**_columns(approval)))
            return approval
        except PersistenceError as error:
            # The partial unique index refused a second active request for this operation:
            # someone created it concurrently, so use theirs.
            if not isinstance(error.__cause__, IntegrityError):
                raise
            existing = await self.active_for(approval.operation_digest)
            if existing is None:
                raise
            return existing

    async def get(self, approval_id: UUID) -> Approval | None:
        async with persistence_transaction(self._factory, "approval.get") as db:
            row = await db.get(ApprovalRow, approval_id)
            return None if row is None else _load(row)

    async def active_for(self, operation_digest: str) -> Approval | None:
        async with persistence_transaction(self._factory, "approval.active") as db:
            row = (
                await db.execute(
                    select(ApprovalRow).where(ApprovalRow.operation_digest == operation_digest, ApprovalRow.state.in_(_ACTIVE)).limit(1)
                )
            ).scalar_one_or_none()
            return None if row is None else _load(row)

    async def save(self, current: Approval, updated: Approval) -> Approval:
        saved = _with_version(updated, current.version + 1)
        async with persistence_transaction(self._factory, "approval.save") as db:
            result = await db.execute(
                update(ApprovalRow)
                .where(ApprovalRow.id == current.approval_id, ApprovalRow.version == current.version)
                .values(**_columns(saved))
            )
            if result.rowcount != 1:
                if await db.get(ApprovalRow, current.approval_id) is None:
                    raise PersistenceError("The approval request no longer exists in storage.")
                raise PersistenceConflictError("The approval request changed concurrently.")
        return saved

    async def list(self, states: frozenset[ApprovalState] | None, limit: int) -> tuple[Approval, ...]:
        query = select(ApprovalRow).order_by(ApprovalRow.created_at.desc()).limit(limit)
        if states is not None:
            query = query.where(ApprovalRow.state.in_([state.value for state in states]))
        async with persistence_transaction(self._factory, "approval.list") as db:
            rows = list((await db.execute(query)).scalars())
        loaded: list[Approval] = []
        for row in rows:
            try:
                loaded.append(_load(row))
            except PersistenceError:
                continue  # listed nowhere and usable by nothing; logged above
        return tuple(loaded)

    async def due_for_expiry(self, now: datetime) -> tuple[Approval, ...]:
        async with persistence_transaction(self._factory, "approval.due") as db:
            rows = (
                await db.execute(select(ApprovalRow).where(ApprovalRow.state.in_(_ACTIVE), ApprovalRow.expires_at <= now))
            ).scalars()
            return tuple(_load(row) for row in rows)


def _with_version(approval: Approval, version: int) -> Approval:
    return replace(approval, version=version)


def _load(row: ApprovalRow) -> Approval:
    """A stored request that can't be read (unknown state, operation not matching its
    digest) fails closed: it can't be decided or consumed."""
    try:
        return _from_row(row)
    except (ValueError, TypeError, KeyError) as error:
        logger.error("Stored approval request is invalid", extra={"genesis_context": {"approval_id": str(row.id), "error_type": type(error).__name__}})
        raise PersistenceError("A stored approval request is invalid and can't be used.") from error


def _columns(approval: Approval) -> dict[str, object]:
    binding = approval.binding
    return {
        "id": approval.approval_id,
        "state": approval.state.value,
        "caller": binding.caller,
        "subject": dict(binding.subject),
        "tool_name": binding.tool_name,
        "tool_version": binding.tool_version,
        "tool_contract": binding.tool_contract,
        "arguments": dict(binding.arguments),
        "operation_digest": approval.operation_digest,
        "reason": approval.reason,
        "created_at": approval.created_at,
        "expires_at": approval.expires_at,
        "decided_at": approval.decided_at,
        "decision_source": None if approval.decision_source is None else approval.decision_source.value,
        "consumed_at": approval.consumed_at,
        "task_id": approval.task_id,
        "outcome": None if approval.outcome is None else approval.outcome.value,
        "detail": approval.detail,
        "version": approval.version,
    }


def _from_row(row: ApprovalRow) -> Approval:
    # Approval.__post_init__ recomputes the digest from the stored operation and refuses a
    # record whose operation no longer matches it, so a tampered row can't authorize anything.
    return Approval(
        approval_id=row.id,
        state=ApprovalState(row.state),
        binding=OperationBinding(
            caller=row.caller,
            subject={str(key): str(value) for key, value in dict(row.subject).items()},
            tool_name=row.tool_name,
            tool_version=row.tool_version,
            tool_contract=row.tool_contract,
            arguments=dict(row.arguments),
        ),
        operation_digest=row.operation_digest,
        reason=row.reason,
        created_at=_aware(row.created_at),
        expires_at=_aware(row.expires_at),
        decided_at=None if row.decided_at is None else _aware(row.decided_at),
        decision_source=None if row.decision_source is None else DecisionSource(row.decision_source),
        consumed_at=None if row.consumed_at is None else _aware(row.consumed_at),
        task_id=row.task_id,
        outcome=None if row.outcome is None else ApprovalOutcome(row.outcome),
        detail=row.detail,
        version=row.version,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
