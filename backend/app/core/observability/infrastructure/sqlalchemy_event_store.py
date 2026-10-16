"""SQLAlchemy adapter for the runtime event store port."""

from datetime import UTC, datetime

from sqlalchemy import delete, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.observability.application.runtime_event_store import RuntimeEventStore
from backend.app.core.observability.domain.runtime_event import EventQuery, StoredEvent
from backend.app.core.observability.infrastructure.orm import RuntimeEventRow
from backend.app.database.transactions import persistence_transaction


class SqlAlchemyRuntimeEventStore(RuntimeEventStore):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def append(self, events: tuple[StoredEvent, ...]) -> None:
        if not events:
            return
        async with persistence_transaction(self._factory, "runtime_event.append") as db:
            known = set(
                (await db.scalars(select(RuntimeEventRow.event_id).where(RuntimeEventRow.event_id.in_([e.event_id for e in events])))).all()
            )
            rows = [_columns(event) for event in events if event.event_id not in known]  # a retried batch is not stored twice
            if rows:
                await db.execute(insert(RuntimeEventRow), rows)

    async def page(self, query: EventQuery, *, before_sequence: int | None, limit: int) -> tuple[StoredEvent, ...]:
        statement = select(RuntimeEventRow).order_by(RuntimeEventRow.sequence.desc()).limit(limit)
        if before_sequence is not None:
            statement = statement.where(RuntimeEventRow.sequence < before_sequence)
        if query.execution_id is not None:
            statement = statement.where(or_(RuntimeEventRow.execution_id == query.execution_id, RuntimeEventRow.interaction_id == query.execution_id))
        if query.workflow_id is not None:
            statement = statement.where(RuntimeEventRow.workflow_id == query.workflow_id)
        if query.approval_id is not None:
            statement = statement.where(RuntimeEventRow.approval_id == query.approval_id)
        if query.tool_task_id is not None:
            statement = statement.where(RuntimeEventRow.tool_task_id == query.tool_task_id)
        if query.event_type is not None:
            if query.event_type.endswith("."):
                escaped = query.event_type.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                statement = statement.where(RuntimeEventRow.event_type.like(f"{escaped}%", escape="\\"))
            else:
                statement = statement.where(RuntimeEventRow.event_type == query.event_type)
        async with persistence_transaction(self._factory, "runtime_event.page") as db:
            return tuple(_from_row(row) for row in (await db.scalars(statement)).all())

    async def prune(self, older_than: datetime) -> int:
        async with persistence_transaction(self._factory, "runtime_event.prune") as db:
            result = await db.execute(delete(RuntimeEventRow).where(RuntimeEventRow.occurred_at < older_than))
        return int(result.rowcount or 0)


def _columns(event: StoredEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "source": event.source,
        "occurred_at": event.occurred_at,
        "execution_id": event.execution_id,
        "interaction_id": event.interaction_id,
        "agent_id": event.agent_id,
        "workflow_id": event.workflow_id,
        "step_id": event.step_id,
        "tool_task_id": event.tool_task_id,
        "approval_id": event.approval_id,
        "payload": dict(event.payload),
    }


def _from_row(row: RuntimeEventRow) -> StoredEvent:
    return StoredEvent(
        sequence=row.sequence,
        event_id=row.event_id,
        event_type=row.event_type,
        source=row.source,
        occurred_at=row.occurred_at if row.occurred_at.tzinfo is not None else row.occurred_at.replace(tzinfo=UTC),
        payload=dict(row.payload or {}),
        execution_id=row.execution_id,
        interaction_id=row.interaction_id,
        agent_id=row.agent_id,
        workflow_id=row.workflow_id,
        step_id=row.step_id,
        tool_task_id=row.tool_task_id,
        approval_id=row.approval_id,
    )
