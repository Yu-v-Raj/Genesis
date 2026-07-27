"""Unit tests for the Agent Runtime metadata registry."""

from uuid import uuid4

import pytest

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.exceptions import AgentNotFoundError, DuplicateAgentError
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import (
    AgentMetadataUpdated,
    AgentRegistered,
    AgentRemoved,
    AgentStatusChanged,
    Event,
)


def example_agent() -> Agent:
    """Create an Agent Runtime record for registry tests."""
    return Agent(
        name="researcher",
        description="Collects information for a future workflow.",
        type="research",
        metadata={"priority": "normal"},
        tags=("example", "research"),
    )


@pytest.mark.asyncio
async def test_register_get_list_exists_and_count() -> None:
    """The registry exposes consistent Agent metadata snapshots."""
    registry = AgentRegistry(EventBus())
    agent = example_agent()

    assert await registry.register(agent) is agent
    assert registry.get(agent.id) is agent
    assert registry.list() == (agent,)
    assert registry.exists(agent.id)
    assert registry.count() == 1


@pytest.mark.asyncio
async def test_duplicate_and_unknown_agents_raise_clear_errors() -> None:
    """Duplicate registration and unknown lookups are rejected."""
    registry = AgentRegistry(EventBus())
    agent = example_agent()
    await registry.register(agent)

    with pytest.raises(DuplicateAgentError):
        await registry.register(agent)
    with pytest.raises(AgentNotFoundError):
        registry.get(uuid4())


@pytest.mark.asyncio
async def test_removal_publishes_agent_removed_event() -> None:
    """Removing an Agent emits the required lifecycle event."""
    event_bus = EventBus()
    received: list[Event] = []
    event_bus.subscribe(received.append)
    registry = AgentRegistry(event_bus)
    agent = example_agent()
    await registry.register(agent)

    assert await registry.unregister(agent.id) is agent
    assert isinstance(received[-1], AgentRemoved)
    assert received[-1].payload == {"agent_id": str(agent.id)}
    assert registry.count() == 0


@pytest.mark.asyncio
async def test_registration_and_status_metadata_changes_publish_events() -> None:
    """Registry state transitions are observable through the existing Event Bus."""
    event_bus = EventBus()
    received: list[Event] = []
    event_bus.subscribe(received.append)
    registry = AgentRegistry(event_bus)
    agent = example_agent()

    await registry.register(agent)
    running_agent = await registry.update_status(agent.id, AgentStatus.RUNNING)
    updated_agent = await registry.update_metadata(agent.id, {"priority": "high"})

    assert isinstance(received[0], AgentRegistered)
    assert isinstance(received[1], AgentStatusChanged)
    assert isinstance(received[2], AgentMetadataUpdated)
    assert running_agent.status is AgentStatus.RUNNING
    assert updated_agent.metadata["priority"] == "high"
    assert agent.status is AgentStatus.CREATED
    assert agent.metadata["priority"] == "normal"


def test_agent_collections_are_immutable_snapshots() -> None:
    """Agent records freeze tags and metadata at their domain boundary."""
    agent = example_agent()

    with pytest.raises(TypeError):
        agent.metadata["priority"] = "high"  # type: ignore[index]
    assert agent.tags == ("example", "research")
