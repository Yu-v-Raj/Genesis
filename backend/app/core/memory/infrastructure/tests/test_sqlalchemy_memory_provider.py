"""Durable memory storage (SQLite, and PostgreSQL when configured)."""

import pytest

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.infrastructure.sqlalchemy_repositories import SqlAlchemyAgentRepository
from backend.app.core.core_services.persistence import PersistenceError
from backend.app.core.memory.domain.memory_kind import MemoryKind
from backend.app.core.memory.domain.memory_record import MemoryRecord
from backend.app.core.memory.infrastructure.sqlalchemy_provider import SqlAlchemyMemoryProvider


async def agent_id(factory):
    agent = Agent(name="a", description="d", type="t")
    await SqlAlchemyAgentRepository(factory).add(agent)
    return agent.id


@pytest.mark.asyncio
async def test_memories_round_trip_and_survive_a_new_provider(session_factory) -> None:
    owner = await agent_id(session_factory)
    memory = await SqlAlchemyMemoryProvider(session_factory).create(
        MemoryRecord(agent_id=owner, content="Prefers metric.", kind=MemoryKind.PREFERENCE, tags=("units",), metadata={"source": "chat"})
    )

    fresh = SqlAlchemyMemoryProvider(session_factory)
    stored = await fresh.get(memory.memory_id)
    assert stored is not None
    assert (stored.content, stored.kind, stored.tags, dict(stored.metadata)) == ("Prefers metric.", MemoryKind.PREFERENCE, ("units",), {"source": "chat"})
    assert [m.memory_id for m in await fresh.search("METRIC", owner)] == [memory.memory_id]
    assert [m.memory_id for m in await fresh.search("units", owner)] == [memory.memory_id]

    updated = await fresh.update(stored.with_updates(content="Prefers imperial."))
    assert updated is not None and (await fresh.get(memory.memory_id)).content == "Prefers imperial."
    assert await fresh.count(owner) == 1


@pytest.mark.asyncio
async def test_memories_are_scoped_and_deleted_with_their_agent(session_factory) -> None:
    provider = SqlAlchemyMemoryProvider(session_factory)
    first, second = await agent_id(session_factory), await agent_id(session_factory)
    await provider.create(MemoryRecord(agent_id=first, content="first's"))
    kept = await provider.create(MemoryRecord(agent_id=second, content="second's"))

    assert [m.content for m in await provider.list(first)] == ["first's"]
    await SqlAlchemyAgentRepository(session_factory).delete(first)

    assert await provider.list(first) == ()
    assert [m.memory_id for m in await provider.list()] == [kept.memory_id]


@pytest.mark.asyncio
async def test_memories_need_an_existing_agent(session_factory) -> None:
    with pytest.raises(PersistenceError):
        await SqlAlchemyMemoryProvider(session_factory).create(MemoryRecord(agent_id=Agent(name="a", description="d", type="t").id, content="x"))
