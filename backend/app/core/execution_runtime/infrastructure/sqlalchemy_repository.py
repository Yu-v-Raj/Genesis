"""SQLAlchemy adapter for the durable execution repository port."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.execution_runtime.application.repositories import ExecutionRepository
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_result import ExecutionResult
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus
from backend.app.core.execution_runtime.domain.lifecycle import TERMINAL_STATUSES
from backend.app.core.execution_runtime.domain.transition import ExecutionTransition
from backend.app.core.execution_runtime.infrastructure.orm import ExecutionRow, ExecutionTransitionRow
from backend.app.database.transactions import persistence_transaction


_LEASED = (ExecutionStatus.STARTING.value, ExecutionStatus.RUNNING.value)


class SqlAlchemyExecutionRepository(ExecutionRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def add(self, execution: Execution, *, detail: str | None = None) -> Execution:
        stored = _with_version(execution, 1)
        async with persistence_transaction(self._factory, "execution.add") as db:
            await db.execute(insert(ExecutionRow).values(**_columns(stored)))
            await _record(db, stored, None, detail)
        return stored

    async def transition(
        self, current: Execution, updated: Execution, *, detail: str | None = None
    ) -> Execution:
        saved = _with_version(updated, current.version + 1)
        async with persistence_transaction(self._factory, "execution.transition") as db:
            result = await db.execute(
                update(ExecutionRow)
                .where(ExecutionRow.id == current.execution_id, ExecutionRow.version == current.version)
                .values(**_columns(saved))
            )
            if result.rowcount != 1:
                if await db.get(ExecutionRow, current.execution_id) is None:
                    raise PersistenceError("The execution no longer exists in storage.")
                raise PersistenceConflictError("The execution changed concurrently.")
            if saved.status is not current.status:
                await _record(db, saved, current.status, detail)
        return saved

    async def get(self, execution_id: UUID) -> Execution | None:
        async with persistence_transaction(self._factory, "execution.get") as db:
            row = await db.get(ExecutionRow, execution_id)
            return None if row is None else _from_row(row)

    async def list(self, agent_id: UUID | None = None, limit: int = 200) -> tuple[Execution, ...]:
        query = select(ExecutionRow).order_by(ExecutionRow.created_at.desc()).limit(limit)
        if agent_id is not None:
            query = query.where(ExecutionRow.agent_id == agent_id)
        async with persistence_transaction(self._factory, "execution.list") as db:
            return tuple(_from_row(row) for row in (await db.scalars(query)).all())

    async def history(self, execution_id: UUID) -> tuple[ExecutionTransition, ...]:
        async with persistence_transaction(self._factory, "execution.history") as db:
            rows = (
                await db.scalars(
                    select(ExecutionTransitionRow)
                    .where(ExecutionTransitionRow.execution_id == execution_id)
                    .order_by(ExecutionTransitionRow.sequence)
                )
            ).all()
        return tuple(
            ExecutionTransition(
                execution_id=row.execution_id,
                sequence=row.sequence,
                from_status=None if row.from_status is None else ExecutionStatus(row.from_status),
                to_status=ExecutionStatus(row.to_status),
                at=_aware(row.at),
                detail=row.detail,
            )
            for row in rows
        )

    async def claim_next(self, owner: str, lease_expires_at: datetime) -> Execution | None:
        # A few attempts: losing a race to another worker just means trying the next row.
        for _ in range(5):
            async with persistence_transaction(self._factory, "execution.claim") as db:
                row = await db.scalar(
                    select(ExecutionRow)
                    .where(ExecutionRow.status == ExecutionStatus.QUEUED.value)
                    .order_by(ExecutionRow.created_at)
                    .limit(1)
                )
                if row is None:
                    return None
                current = _from_row(row)
                claimed = _with_version(
                    current.with_status(ExecutionStatus.STARTING, lease_owner=owner, lease_expires_at=lease_expires_at),
                    current.version + 1,
                )
                result = await db.execute(
                    update(ExecutionRow)
                    .where(
                        ExecutionRow.id == current.execution_id,
                        ExecutionRow.version == current.version,
                        ExecutionRow.status == ExecutionStatus.QUEUED.value,
                    )
                    .values(**_columns(claimed))
                )
                if result.rowcount == 1:
                    await _record(db, claimed, current.status, f"claimed by {owner}")
                    return claimed
        return None

    async def renew_lease(self, execution_id: UUID, owner: str, lease_expires_at: datetime) -> bool:
        async with persistence_transaction(self._factory, "execution.renew_lease") as db:
            result = await db.execute(
                update(ExecutionRow)
                .where(
                    ExecutionRow.id == execution_id,
                    ExecutionRow.lease_owner == owner,
                    ExecutionRow.status.in_(_LEASED),
                )
                .values(lease_expires_at=lease_expires_at)
            )
        return result.rowcount == 1

    async def expired_leases(self, now: datetime) -> tuple[Execution, ...]:
        async with persistence_transaction(self._factory, "execution.expired_leases") as db:
            rows = (
                await db.scalars(
                    select(ExecutionRow).where(
                        ExecutionRow.status.in_(_LEASED),
                        (ExecutionRow.lease_expires_at.is_(None)) | (ExecutionRow.lease_expires_at < now),
                    )
                )
            ).all()
        return tuple(_from_row(row) for row in rows)


async def _record(db: AsyncSession, execution: Execution, previous: ExecutionStatus | None, detail: str | None) -> None:
    sequence = await db.scalar(
        select(func.coalesce(func.max(ExecutionTransitionRow.sequence), 0)).where(
            ExecutionTransitionRow.execution_id == execution.execution_id
        )
    )
    await db.execute(
        insert(ExecutionTransitionRow).values(
            execution_id=execution.execution_id,
            sequence=int(sequence or 0) + 1,
            from_status=None if previous is None else previous.value,
            to_status=execution.status.value,
            at=execution.updated_at or datetime.now(UTC),
            detail=detail,
        )
    )


def _with_version(execution: Execution, version: int) -> Execution:
    return replace(execution, version=version, updated_at=execution.updated_at or datetime.now(UTC))


def _columns(execution: Execution) -> dict[str, object]:
    result = execution.result
    return {
        "id": execution.execution_id,
        "agent_id": execution.agent_id,
        "status": execution.status.value,
        "attempt": execution.attempt,
        "retry_of": execution.retry_of,
        "execution_metadata": dict(execution.metadata),
        "current_step": execution.current_step,
        "result_output": None if result is None else result.output,
        "result_duration": None if result is None else result.duration,
        "error": execution.error,
        "error_category": execution.error_category,
        "created_at": execution.created_at,
        "started_at": execution.started_at,
        "finished_at": execution.finished_at,
        "updated_at": execution.updated_at,
        "lease_owner": execution.lease_owner,
        "lease_expires_at": execution.lease_expires_at,
        "version": execution.version,
    }


def _from_row(row: ExecutionRow) -> Execution:
    status = ExecutionStatus(row.status)
    has_result = status in TERMINAL_STATUSES and status is not ExecutionStatus.INTERRUPTED
    return Execution(
        execution_id=row.id,
        agent_id=row.agent_id,
        status=status,
        attempt=row.attempt,
        retry_of=row.retry_of,
        metadata=row.execution_metadata or {},
        current_step=row.current_step,
        result=(
            ExecutionResult(status=status, output=row.result_output, duration=row.result_duration)
            if has_result
            else None
        ),
        error=row.error,
        error_category=row.error_category,
        created_at=_aware(row.created_at),
        started_at=None if row.started_at is None else _aware(row.started_at),
        finished_at=None if row.finished_at is None else _aware(row.finished_at),
        updated_at=_aware(row.updated_at),
        lease_owner=row.lease_owner,
        lease_expires_at=None if row.lease_expires_at is None else _aware(row.lease_expires_at),
        version=row.version,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
