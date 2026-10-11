"""Durable MemoryProvider backed by the shared SQLAlchemy database."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.core_services.persistence import PersistenceError
from backend.app.core.memory.application.memory_provider import MemoryProvider
from backend.app.core.memory.domain.memory_kind import MemoryKind
from backend.app.core.memory.domain.memory_record import MemoryRecord
from backend.app.core.memory.infrastructure.orm import MemoryRow
from backend.app.database.transactions import persistence_transaction


class SqlAlchemyMemoryProvider(MemoryProvider):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def create(self, memory: MemoryRecord) -> MemoryRecord:
        try:
            async with persistence_transaction(self._factory, "memory.create") as db:
                await db.execute(insert(MemoryRow).values(**_columns(memory)))
        except PersistenceError as error:
            if isinstance(error.__cause__, IntegrityError):
                raise PersistenceError("The Agent for this memory no longer exists.") from error.__cause__
            raise
        return memory

    async def get(self, memory_id: UUID) -> MemoryRecord | None:
        async with persistence_transaction(self._factory, "memory.get") as db:
            row = await db.get(MemoryRow, memory_id)
            return None if row is None else _record(row)

    async def list(self, agent_id: UUID | None = None) -> tuple[MemoryRecord, ...]:
        query = select(MemoryRow).order_by(MemoryRow.created_at.desc(), MemoryRow.id)
        if agent_id is not None:
            query = query.where(MemoryRow.agent_id == agent_id)
        async with persistence_transaction(self._factory, "memory.list") as db:
            return tuple(_record(row) for row in (await db.scalars(query)).all())

    async def search(self, query: str, agent_id: UUID) -> tuple[MemoryRecord, ...]:
        # Same semantics as the in-memory provider (case-insensitive substring over
        # content, tags, and metadata), evaluated per Agent.
        needle = query.casefold()
        return tuple(
            item
            for item in await self.list(agent_id)
            if needle in item.content.casefold()
            or needle in " ".join(item.tags).casefold()
            or needle in str(item.metadata).casefold()
        )

    async def update(self, memory: MemoryRecord) -> MemoryRecord | None:
        async with persistence_transaction(self._factory, "memory.update") as db:
            result = await db.execute(
                update(MemoryRow).where(MemoryRow.id == memory.memory_id).values(**_columns(memory))
            )
        return memory if result.rowcount == 1 else None

    async def delete(self, memory_id: UUID) -> MemoryRecord | None:
        async with persistence_transaction(self._factory, "memory.delete") as db:
            row = await db.get(MemoryRow, memory_id)
            if row is None:
                return None
            record = _record(row)
            await db.execute(delete(MemoryRow).where(MemoryRow.id == memory_id))
        return record

    async def count(self, agent_id: UUID | None = None) -> int:
        query = select(func.count()).select_from(MemoryRow)
        if agent_id is not None:
            query = query.where(MemoryRow.agent_id == agent_id)
        async with persistence_transaction(self._factory, "memory.count") as db:
            return int(await db.scalar(query) or 0)


def _columns(memory: MemoryRecord) -> dict[str, object]:
    return {
        "id": memory.memory_id,
        "agent_id": memory.agent_id,
        "content": memory.content,
        "kind": memory.kind.value,
        "memory_metadata": dict(memory.metadata),
        "tags": list(memory.tags),
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def _record(row: MemoryRow) -> MemoryRecord:
    return MemoryRecord(
        memory_id=row.id,
        agent_id=row.agent_id,
        content=row.content,
        kind=MemoryKind(row.kind),
        metadata=row.memory_metadata or {},
        tags=tuple(row.tags or ()),
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
