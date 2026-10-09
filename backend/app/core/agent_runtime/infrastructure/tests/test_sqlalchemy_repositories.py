"""Integration tests for the SQLAlchemy Agent and session repositories."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.exceptions import DuplicateAgentError
from backend.app.core.agent_runtime.domain.session import AgentSession
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.agent_runtime.infrastructure.sqlalchemy_repositories import (
    SqlAlchemyAgentRepository,
    SqlAlchemySessionRepository,
)
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.llm_runtime.domain.models import LLMModel, Message, MessageRole, ToolCall
from backend.app.database import create_database_engine, create_session_factory


Factory = async_sessionmaker[AsyncSession]


def agent(**overrides: object) -> Agent:
    return Agent(
        name="Math helper",
        description="Does arithmetic.",
        type="assistant",
        tags=("math",),
        metadata={"team": "core", "nested": {"a": [1, 2]}},
        llm_model=LLMModel(provider="gemini", model_name="gemini-3.6-flash"),
        allowed_tools=("calculator", "echo"),
        instructions="Use the calculator.",
        **overrides,
    )


def turn(interaction: str = "i-1") -> list[Message]:
    return [
        Message(role=MessageRole.USER, content="Calculate 25 * 4", metadata={"interaction_id": interaction}),
        Message(
            role=MessageRole.ASSISTANT,
            content="",
            metadata={
                "interaction_id": interaction,
                "tool_calls": (
                    ToolCall(
                        call_id="call-1",
                        name="calculator",
                        arguments={"expression": "25 * 4"},
                        metadata={"thought_signature": b"\x00signed\xff"},
                    ),
                ),
            },
        ),
        Message(
            role=MessageRole.TOOL,
            content='{"success": true, "result": 100}',
            metadata={"interaction_id": interaction, "tool_call_id": "call-1", "tool_name": "calculator", "tool_status": "completed"},
        ),
        Message(role=MessageRole.ASSISTANT, content="It is 100.", metadata={"interaction_id": interaction}),
    ]


@pytest.mark.asyncio
async def test_agent_definition_round_trips(session_factory: Factory) -> None:
    repository = SqlAlchemyAgentRepository(session_factory)
    original = agent()

    await repository.add(original)
    (stored,) = await SqlAlchemyAgentRepository(session_factory).list()

    for field in ("id", "name", "description", "type", "tags", "llm_model", "allowed_tools", "instructions"):
        assert getattr(stored, field) == getattr(original, field)
    assert dict(stored.metadata) == {"team": "core", "nested": {"a": [1, 2]}}
    assert stored.created_at == original.created_at and stored.created_at.tzinfo is not None
    assert stored.status is AgentStatus.CREATED


@pytest.mark.asyncio
async def test_duplicate_agent_ids_are_rejected(session_factory: Factory) -> None:
    repository = SqlAlchemyAgentRepository(session_factory)
    original = agent()
    await repository.add(original)

    with pytest.raises(DuplicateAgentError):
        await SqlAlchemyAgentRepository(session_factory).add(original)


@pytest.mark.asyncio
async def test_live_statuses_are_stored_as_restoration_categories(session_factory: Factory) -> None:
    repository = SqlAlchemyAgentRepository(session_factory)
    original = agent()
    await repository.add(original)

    for live, stored in (
        (AgentStatus.IDLE, AgentStatus.IDLE),
        (AgentStatus.RUNNING, AgentStatus.IDLE),
        (AgentStatus.PAUSED, AgentStatus.IDLE),
        (AgentStatus.INITIALIZING, AgentStatus.CREATED),
        (AgentStatus.STOPPED, AgentStatus.STOPPED),
    ):
        await repository.save(original.with_status(live))
        assert (await repository.list())[0].status is stored


@pytest.mark.asyncio
async def test_concurrent_writers_cannot_silently_overwrite_each_other(session_factory: Factory) -> None:
    first, second = SqlAlchemyAgentRepository(session_factory), SqlAlchemyAgentRepository(session_factory)
    original = agent()
    await first.add(original)
    await second.list()

    await first.save(original.with_configuration(llm_model=None, allowed_tools=(), instructions="first"))
    with pytest.raises(PersistenceConflictError):
        await second.save(original.with_configuration(llm_model=None, allowed_tools=(), instructions="second"))

    assert (await first.list())[0].instructions == "first"


@pytest.mark.asyncio
async def test_session_turn_round_trips_with_tool_calls_and_signatures(session_factory: Factory) -> None:
    agents, sessions = SqlAlchemyAgentRepository(session_factory), SqlAlchemySessionRepository(session_factory)
    owner = agent()
    await agents.add(owner)
    session = await sessions.create(AgentSession(agent_id=owner.id))

    await sessions.append(session.id, turn(), expected_length=0)
    stored = await SqlAlchemySessionRepository(session_factory).get(session.id)

    assert stored is not None
    assert [m.role for m in stored.messages] == [MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL, MessageRole.ASSISTANT]
    call = stored.messages[1].metadata["tool_calls"][0]
    assert (call.call_id, call.name, dict(call.arguments)) == ("call-1", "calculator", {"expression": "25 * 4"})
    assert call.metadata["thought_signature"] == b"\x00signed\xff"
    assert dict(stored.messages[2].metadata) == {
        "interaction_id": "i-1",
        "tool_call_id": "call-1",
        "tool_name": "calculator",
        "tool_status": "completed",
    }
    (summary,) = await sessions.list_for_agent(owner.id)
    assert (summary.message_count, summary.title) == (4, "Calculate 25 * 4")


@pytest.mark.asyncio
async def test_stale_or_failed_appends_write_nothing(session_factory: Factory) -> None:
    agents, sessions = SqlAlchemyAgentRepository(session_factory), SqlAlchemySessionRepository(session_factory)
    owner = agent()
    await agents.add(owner)
    session = await sessions.create(AgentSession(agent_id=owner.id))
    await sessions.append(session.id, turn("first"), expected_length=0)

    with pytest.raises(PersistenceConflictError):
        await sessions.append(session.id, turn("stale"), expected_length=0)
    invalid = [*turn("broken"), Message(role=MessageRole.SYSTEM, content="never stored")]
    with pytest.raises(ValueError):
        await sessions.append(session.id, invalid, expected_length=4)

    stored = await sessions.get(session.id)
    assert stored is not None
    assert {m.metadata["interaction_id"] for m in stored.messages} == {"first"}
    assert (await sessions.list_for_agent(owner.id))[0].message_count == 4


@pytest.mark.asyncio
async def test_sessions_are_ordered_by_activity_and_scoped_to_their_agent(session_factory: Factory) -> None:
    agents, sessions = SqlAlchemyAgentRepository(session_factory), SqlAlchemySessionRepository(session_factory)
    owner, other = agent(), agent()
    await agents.add(owner)
    await agents.add(other)
    old_time = datetime.now(UTC) - timedelta(hours=1)
    older = await sessions.create(AgentSession(agent_id=owner.id, created_at=old_time, updated_at=old_time))
    newer = await sessions.create(AgentSession(agent_id=owner.id))
    await sessions.create(AgentSession(agent_id=other.id))

    assert [s.id for s in await sessions.list_for_agent(owner.id)] == [newer.id, older.id]
    await sessions.append(older.id, turn(), expected_length=0)
    latest = await sessions.latest_for_agent(owner.id)
    assert latest is not None and latest.id == older.id


@pytest.mark.asyncio
async def test_deleting_an_agent_removes_its_sessions(session_factory: Factory) -> None:
    agents, sessions = SqlAlchemyAgentRepository(session_factory), SqlAlchemySessionRepository(session_factory)
    owner = agent()
    await agents.add(owner)
    session = await sessions.create(AgentSession(agent_id=owner.id))
    await sessions.append(session.id, turn(), expected_length=0)

    await agents.delete(owner.id)

    assert await sessions.get(session.id) is None
    assert await agents.list() == ()


@pytest.mark.asyncio
async def test_sessions_require_an_existing_agent(session_factory: Factory) -> None:
    with pytest.raises(PersistenceError):
        await SqlAlchemySessionRepository(session_factory).create(AgentSession(agent_id=uuid4()))


@pytest.mark.asyncio
async def test_unreachable_database_raises_safe_persistence_error() -> None:
    engine = create_database_engine("postgresql+asyncpg://genesis:sup3r-secret@127.0.0.1:1/genesis")
    try:
        with pytest.raises(PersistenceError) as caught:
            await SqlAlchemyAgentRepository(create_session_factory(engine)).list()
    finally:
        await engine.dispose()
    assert "sup3r-secret" not in str(caught.value)
    assert "127.0.0.1" not in str(caught.value)
