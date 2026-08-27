"""Memory Runtime behavior tests for provider isolation and events."""

from uuid import uuid4
import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.memory.domain.exceptions import MemoryOwnershipError
from backend.app.core.memory.domain.memory_kind import MemoryKind
from backend.app.core.memory.infrastructure.in_memory_provider import InMemoryProvider

@pytest.mark.asyncio
async def test_crud_search_scoping_and_events() -> None:
    bus = EventBus(); events: list[str] = []
    bus.subscribe(lambda event: events.append(event.event_type))
    first, second = uuid4(), uuid4()
    manager = MemoryManager(InMemoryProvider(), bus)
    memory = await manager.create_memory(agent_id=first, content="Genesis remembers tools", kind=MemoryKind.FACT, tags=("tools",))
    assert await manager.search_memories(first, "tools") == (memory,)
    assert await manager.list_memories(second) == ()
    with pytest.raises(MemoryOwnershipError): await manager.get_memory(memory.memory_id, agent_id=second)
    updated = await manager.update_memory(memory.memory_id, agent_id=first, content="Genesis remembers memory")
    assert updated.content.endswith("memory") and updated.updated_at >= memory.updated_at
    assert await manager.count_memories(first) == 1
    assert (await manager.delete_memory(memory.memory_id, agent_id=first)).memory_id == memory.memory_id
    assert {"memory.created", "memory.updated", "memory.deleted"} <= set(events)

@pytest.mark.asyncio
async def test_capacity_evicts_oldest_and_lists_newest_first() -> None:
    agent = uuid4(); manager = MemoryManager(InMemoryProvider(capacity=2))
    first = await manager.create_memory(agent_id=agent, content="first")
    second = await manager.create_memory(agent_id=agent, content="second")
    third = await manager.create_memory(agent_id=agent, content="third")
    listed = await manager.list_memories(agent)
    assert first not in listed and listed == (third, second)
