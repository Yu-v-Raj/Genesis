"""SQLAlchemy adapters for the Agent and session repository ports.

Every public method runs in its own short transaction. Driver and SQLAlchemy errors are
translated into ``PersistenceError`` with messages that never include the database URL,
credentials, or row contents.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.agent_runtime.application.repositories import (
    AgentRepository,
    SessionRepository,
)
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.exceptions import DuplicateAgentError
from backend.app.core.agent_runtime.domain.session import (
    AgentSession,
    AgentSessionSummary,
    session_title,
)
from backend.app.core.agent_runtime.domain.status import AgentStatus, restoration_status
from backend.app.core.agent_runtime.infrastructure.message_codec import (
    message_columns,
    message_from_columns,
)
from backend.app.core.agent_runtime.infrastructure.orm import AgentRow, MessageRow, SessionRow
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.llm_runtime.domain.models import LLMModel, Message, MessageRole
from backend.app.database.transactions import persistence_transaction


class SqlAlchemyAgentRepository(AgentRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory
        # Last version this process read or wrote, per Agent; enables optimistic locking
        # without putting a storage concern on the domain record.
        self._versions: dict[UUID, int] = {}

    async def add(self, agent: Agent) -> None:
        try:
            async with persistence_transaction(self._factory, "agent.add") as session:
                await session.execute(insert(AgentRow).values(**_agent_columns(agent), version=1))
        except PersistenceError as error:
            if isinstance(error.__cause__, IntegrityError):
                raise DuplicateAgentError(agent.id) from error.__cause__
            raise
        self._versions[agent.id] = 1

    async def save(self, agent: Agent) -> None:
        expected = self._versions.get(agent.id)
        async with persistence_transaction(self._factory, "agent.save") as session:
            if expected is None:
                expected = await session.scalar(select(AgentRow.version).where(AgentRow.id == agent.id))
                if expected is None:
                    raise PersistenceError("The Agent no longer exists in storage.")
            result = await session.execute(
                update(AgentRow)
                .where(AgentRow.id == agent.id, AgentRow.version == expected)
                .values(**_agent_columns(agent), version=expected + 1)
            )
            if result.rowcount != 1:
                raise PersistenceConflictError(
                    "This Agent was changed elsewhere. Reload it and try again."
                )
        self._versions[agent.id] = expected + 1

    async def delete(self, agent_id: UUID) -> None:
        async with persistence_transaction(self._factory, "agent.delete") as session:
            await session.execute(delete(AgentRow).where(AgentRow.id == agent_id))
        self._versions.pop(agent_id, None)

    async def list(self) -> tuple[Agent, ...]:
        async with persistence_transaction(self._factory, "agent.list") as session:
            rows = (await session.scalars(select(AgentRow).order_by(AgentRow.created_at, AgentRow.id))).all()
        self._versions.update({row.id: row.version for row in rows})
        return tuple(_agent_from_row(row) for row in rows)


class SqlAlchemySessionRepository(SessionRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def create(self, session: AgentSession) -> AgentSession:
        if session.messages:
            raise ValueError("Sessions are created empty; messages are appended per turn.")
        async with persistence_transaction(self._factory, "session.create") as db:
            await db.execute(
                insert(SessionRow).values(
                    id=session.id,
                    agent_id=session.agent_id,
                    message_count=0,
                    title=None,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                )
            )
        return session

    async def get(self, session_id: UUID) -> AgentSession | None:
        async with persistence_transaction(self._factory, "session.get") as db:
            row = await db.get(SessionRow, session_id)
            if row is None:
                return None
            messages = (
                await db.scalars(
                    select(MessageRow).where(MessageRow.session_id == session_id).order_by(MessageRow.position)
                )
            ).all()
        return _session_from_rows(row, messages)

    async def latest_for_agent(self, agent_id: UUID) -> AgentSession | None:
        async with persistence_transaction(self._factory, "session.latest") as db:
            session_id = await db.scalar(
                select(SessionRow.id)
                .where(SessionRow.agent_id == agent_id)
                .order_by(SessionRow.updated_at.desc(), SessionRow.created_at.desc())
                .limit(1)
            )
        return None if session_id is None else await self.get(session_id)

    async def list_for_agent(self, agent_id: UUID) -> tuple[AgentSessionSummary, ...]:
        async with persistence_transaction(self._factory, "session.list") as db:
            rows = (
                await db.scalars(
                    select(SessionRow)
                    .where(SessionRow.agent_id == agent_id)
                    .order_by(SessionRow.updated_at.desc(), SessionRow.created_at.desc())
                )
            ).all()
        return tuple(
            AgentSessionSummary(
                id=row.id,
                agent_id=row.agent_id,
                created_at=_aware(row.created_at),
                updated_at=_aware(row.updated_at),
                message_count=row.message_count,
                title=row.title,
            )
            for row in rows
        )

    async def append(
        self, session_id: UUID, messages: Sequence[Message], *, expected_length: int
    ) -> AgentSession:
        now = datetime.now(UTC)
        first_user = next((m.content for m in messages if m.role is MessageRole.USER), None)
        try:
            async with persistence_transaction(self._factory, "session.append") as db:
                # Compare-and-set on message_count: only the writer that saw the current
                # length may extend the session, and all of its rows land or none do.
                result = await db.execute(
                    update(SessionRow)
                    .where(SessionRow.id == session_id, SessionRow.message_count == expected_length)
                    .values(
                        message_count=expected_length + len(messages),
                        updated_at=now,
                        title=func.coalesce(SessionRow.title, None if first_user is None else session_title(first_user)),
                    )
                )
                if result.rowcount != 1:
                    exists = await db.scalar(select(SessionRow.id).where(SessionRow.id == session_id))
                    if exists is None:
                        raise PersistenceError("The session no longer exists in storage.")
                    raise PersistenceConflictError(
                        "The conversation changed while this message was processed. Reload and try again."
                    )
                if messages:
                    await db.execute(
                        insert(MessageRow),
                        [
                            {
                                "session_id": session_id,
                                "position": expected_length + offset,
                                "created_at": now,
                                **message_columns(message),
                            }
                            for offset, message in enumerate(messages)
                        ],
                    )
        except PersistenceError as error:
            if isinstance(error.__cause__, IntegrityError):
                raise PersistenceConflictError(
                    "The conversation changed while this message was processed. Reload and try again."
                ) from error.__cause__
            raise
        stored = await self.get(session_id)
        if stored is None:
            raise PersistenceError("The session no longer exists in storage.")
        return stored

    async def delete_for_agent(self, agent_id: UUID) -> None:
        async with persistence_transaction(self._factory, "session.delete_for_agent") as db:
            await db.execute(delete(SessionRow).where(SessionRow.agent_id == agent_id))


def _agent_columns(agent: Agent) -> dict[str, object]:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "type": agent.type,
        "status": restoration_status(agent.status).value,
        "tags": list(agent.tags),
        "agent_metadata": dict(agent.metadata),
        "llm_provider": None if agent.llm_model is None else agent.llm_model.provider,
        "llm_model_name": None if agent.llm_model is None else agent.llm_model.model_name,
        "allowed_tools": list(agent.allowed_tools),
        "instructions": agent.instructions,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


def _agent_from_row(row: AgentRow) -> Agent:
    return Agent(
        id=row.id,
        name=row.name,
        description=row.description,
        type=row.type,
        status=AgentStatus(row.status),
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
        metadata=row.agent_metadata or {},
        tags=tuple(row.tags or ()),
        llm_model=(
            None
            if row.llm_provider is None or row.llm_model_name is None
            else LLMModel(provider=row.llm_provider, model_name=row.llm_model_name)
        ),
        allowed_tools=tuple(row.allowed_tools or ()),
        instructions=row.instructions,
    )


def _session_from_rows(row: SessionRow, messages: Sequence[MessageRow]) -> AgentSession:
    return AgentSession(
        id=row.id,
        agent_id=row.agent_id,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
        messages=tuple(
            message_from_columns(
                role=m.role,
                content=m.content,
                interaction_id=m.interaction_id,
                tool_call_id=m.tool_call_id,
                tool_name=m.tool_name,
                tool_status=m.tool_status,
                tool_calls=m.tool_calls,
            )
            for m in messages
        ),
    )


def _aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; Genesis stores UTC throughout."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
