"""Unit tests for Agent Runtime lifecycle orchestration."""

from uuid import uuid4

import pytest

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.exceptions import (
    AgentLifecycleError,
    AgentNotFoundError,
    DuplicateAgentError,
)
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import Event


def manager_with_events() -> tuple[AgentManager, list[Event]]:
    """Create an isolated manager and capture its published events."""
    event_bus = EventBus()
    received: list[Event] = []
    event_bus.subscribe(received.append)
    return AgentManager(AgentRegistry(event_bus), event_bus), received


@pytest.mark.asyncio
async def test_create_agent_registers_ephemeral_context_and_emits_event() -> None:
    """Creation owns both the registry record and its runtime context."""
    manager, received = manager_with_events()

    agent = await manager.create_agent(
        name="planner", description="Plans future work.", type="planning"
    )

    context = await manager.get_context(agent.id)
    assert agent.status is AgentStatus.CREATED
    assert context.current_state is AgentStatus.CREATED
    assert [event.event_type for event in received] == ["agent.registered", "agent.created"]


@pytest.mark.asyncio
async def test_duplicate_create_and_invalid_lifecycle_transition_raise_domain_errors() -> None:
    """The manager protects registry identity and its strict state machine."""
    manager, _ = manager_with_events()
    agent_id = uuid4()
    await manager.create_agent(
        agent_id=agent_id,
        name="planner",
        description="Plans future work.",
        type="planning",
    )

    with pytest.raises(DuplicateAgentError):
        await manager.create_agent(
            agent_id=agent_id,
            name="second",
            description="Duplicate record.",
            type="planning",
        )
    with pytest.raises(AgentLifecycleError):
        await manager.start_agent(agent_id)


@pytest.mark.asyncio
async def test_lifecycle_operations_follow_the_supported_transition_sequence() -> None:
    """Initialization, execution controls, completion, and stop update context too."""
    manager, received = manager_with_events()
    agent = await manager.create_agent(
        name="planner", description="Plans future work.", type="planning"
    )

    assert (await manager.initialize_agent(agent.id)).status is AgentStatus.IDLE
    assert (await manager.start_agent(agent.id)).status is AgentStatus.RUNNING
    assert (await manager.pause_agent(agent.id)).status is AgentStatus.PAUSED
    assert (await manager.resume_agent(agent.id)).status is AgentStatus.RUNNING
    assert (await manager.complete_agent(agent.id)).status is AgentStatus.COMPLETED
    assert (await manager.stop_agent(agent.id)).status is AgentStatus.STOPPED
    assert (await manager.get_context(agent.id)).current_state is AgentStatus.STOPPED
    assert [event.event_type for event in received if event.event_type.startswith("agent.")] == [
        "agent.registered",
        "agent.created",
        "agent.status_changed",
        "agent.status_changed",
        "agent.initialized",
        "agent.status_changed",
        "agent.started",
        "agent.status_changed",
        "agent.paused",
        "agent.status_changed",
        "agent.resumed",
        "agent.status_changed",
        "agent.completed",
        "agent.status_changed",
        "agent.stopped",
    ]


@pytest.mark.asyncio
async def test_stop_is_allowed_from_created_and_terminal_states_are_protected() -> None:
    """Stopping is universal, whereas terminal Agents cannot resume execution."""
    manager, _ = manager_with_events()
    agent = await manager.create_agent(
        name="planner", description="Plans future work.", type="planning"
    )

    assert (await manager.stop_agent(agent.id)).status is AgentStatus.STOPPED
    assert (await manager.stop_agent(agent.id)).status is AgentStatus.STOPPED
    with pytest.raises(AgentLifecycleError):
        await manager.start_agent(agent.id)


@pytest.mark.asyncio
async def test_metadata_and_context_are_kept_in_their_separate_boundaries() -> None:
    """Persistent Agent metadata remains distinct from runtime-only context data."""
    manager, received = manager_with_events()
    agent = await manager.create_agent(
        name="planner",
        description="Plans future work.",
        type="planning",
        metadata={"priority": "low"},
    )

    updated_agent = await manager.update_metadata(agent.id, {"priority": "high"})
    context = await manager.update_context(
        agent.id,
        current_task="prepare plan",
        temporary_variables={"attempt": 1},
        runtime_metadata={"worker": "local"},
    )

    assert updated_agent.metadata == {"priority": "high"}
    assert context.current_task == "prepare plan"
    assert context.temporary_variables == {"attempt": 1}
    assert context.runtime_metadata == {"worker": "local"}
    assert received[-1].event_type == "agent.context_updated"


@pytest.mark.asyncio
async def test_delete_removes_context_and_agent_record() -> None:
    """Deletion removes both in-memory representations as one operation."""
    manager, _ = manager_with_events()
    agent = await manager.create_agent(
        name="planner", description="Plans future work.", type="planning"
    )

    assert await manager.delete_agent(agent.id) is agent
    with pytest.raises(AgentNotFoundError):
        await manager.get_context(agent.id)
