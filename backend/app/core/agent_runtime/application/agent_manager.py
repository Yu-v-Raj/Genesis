"""Lifecycle orchestration for Genesis Agent Runtime records."""

import asyncio
from collections.abc import Mapping
from uuid import UUID

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.context import AgentContext, UNSET
from backend.app.core.agent_runtime.domain.exceptions import AgentLifecycleError
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import (
    AgentCompleted,
    AgentContextUpdated,
    AgentCreated,
    AgentDeleted,
    AgentFailed,
    AgentInitialized,
    AgentPaused,
    AgentResumed,
    AgentStarted,
    AgentStopped,
)


class AgentManager:
    """Create Agent records and coordinate their lifecycle and runtime contexts."""

    _ALLOWED_TRANSITIONS = {
        AgentStatus.CREATED: {AgentStatus.INITIALIZING, AgentStatus.STOPPED},
        AgentStatus.INITIALIZING: {AgentStatus.IDLE, AgentStatus.STOPPED},
        AgentStatus.IDLE: {AgentStatus.RUNNING, AgentStatus.STOPPED},
        AgentStatus.RUNNING: {
            AgentStatus.WAITING,
            AgentStatus.PAUSED,
            AgentStatus.COMPLETED,
            AgentStatus.FAILED,
            AgentStatus.STOPPED,
        },
        AgentStatus.WAITING: {AgentStatus.RUNNING, AgentStatus.STOPPED},
        AgentStatus.PAUSED: {AgentStatus.RUNNING, AgentStatus.STOPPED},
        AgentStatus.COMPLETED: {AgentStatus.STOPPED},
        AgentStatus.FAILED: {AgentStatus.STOPPED},
        AgentStatus.STOPPED: set(),
    }

    def __init__(self, registry: AgentRegistry, event_bus: EventBus) -> None:
        self._registry = registry
        self._event_bus = event_bus
        self._contexts: dict[UUID, AgentContext] = {}
        self._lock = asyncio.Lock()

    async def create_agent(
        self,
        *,
        name: str,
        description: str,
        type: str,
        agent_id: UUID | None = None,
        metadata: Mapping[str, object] | None = None,
        tags: tuple[str, ...] = (),
    ) -> Agent:
        """Create an Agent record and its ephemeral runtime context."""
        agent = Agent(
            name=name,
            description=description,
            type=type,
            **({} if agent_id is None else {"id": agent_id}),
            metadata={} if metadata is None else metadata,
            tags=tags,
        )
        async with self._lock:
            await self._registry.register(agent)
            self._contexts[agent.id] = AgentContext(current_state=agent.status)
        await self._event_bus.publish(
            AgentCreated(source="agent_manager", payload={"agent_id": str(agent.id)})
        )
        return agent

    async def delete_agent(self, agent_id: UUID) -> Agent:
        """Remove an Agent and its runtime-only context."""
        async with self._lock:
            agent = await self._registry.unregister(agent_id)
            self._contexts.pop(agent_id, None)
        await self._event_bus.publish(
            AgentDeleted(source="agent_manager", payload={"agent_id": str(agent_id)})
        )
        return agent

    async def initialize_agent(self, agent_id: UUID) -> Agent:
        """Synchronously initialize an Agent through INITIALIZING to IDLE."""
        async with self._lock:
            agent = self._registry.get(agent_id)
            self._require_transition(agent, AgentStatus.INITIALIZING)
            await self._registry.update_status(agent_id, AgentStatus.INITIALIZING)
            initialized_agent = await self._registry.update_status(agent_id, AgentStatus.IDLE)
            self._contexts[agent_id] = self._contexts[agent_id].with_state(AgentStatus.IDLE)
        await self._event_bus.publish(
            AgentInitialized(source="agent_manager", payload={"agent_id": str(agent_id)})
        )
        return initialized_agent

    async def start_agent(self, agent_id: UUID) -> Agent:
        """Transition an IDLE Agent to RUNNING."""
        return await self._transition(agent_id, AgentStatus.RUNNING, AgentStarted)

    async def pause_agent(self, agent_id: UUID) -> Agent:
        """Transition a RUNNING Agent to PAUSED."""
        return await self._transition(agent_id, AgentStatus.PAUSED, AgentPaused)

    async def resume_agent(self, agent_id: UUID) -> Agent:
        """Transition a PAUSED Agent to RUNNING."""
        return await self._transition(agent_id, AgentStatus.RUNNING, AgentResumed)

    async def complete_agent(self, agent_id: UUID) -> Agent:
        """Transition a RUNNING Agent to COMPLETED."""
        return await self._transition(agent_id, AgentStatus.COMPLETED, AgentCompleted)

    async def fail_agent(self, agent_id: UUID) -> Agent:
        """Transition a RUNNING Agent to FAILED."""
        return await self._transition(agent_id, AgentStatus.FAILED, AgentFailed)

    async def stop_agent(self, agent_id: UUID) -> Agent:
        """Transition an Agent from any non-stopped state to STOPPED."""
        return await self._transition(agent_id, AgentStatus.STOPPED, AgentStopped)

    async def update_metadata(self, agent_id: UUID, metadata: Mapping[str, object]) -> Agent:
        """Delegate Agent metadata updates to the metadata-only registry."""
        async with self._lock:
            return await self._registry.update_metadata(agent_id, metadata)

    async def get_context(self, agent_id: UUID) -> AgentContext:
        """Return the runtime-only context for an existing Agent."""
        async with self._lock:
            self._registry.get(agent_id)
            return self._contexts[agent_id]

    async def update_context(
        self,
        agent_id: UUID,
        *,
        current_task: str | None | object = UNSET,
        temporary_variables: Mapping[str, object] | None = None,
        runtime_metadata: Mapping[str, object] | None = None,
    ) -> AgentContext:
        """Update ephemeral context fields without changing Agent metadata."""
        async with self._lock:
            self._registry.get(agent_id)
            context = self._contexts[agent_id].with_updates(
                current_task=current_task,
                temporary_variables=temporary_variables,
                runtime_metadata=runtime_metadata,
            )
            self._contexts[agent_id] = context
        await self._event_bus.publish(
            AgentContextUpdated(source="agent_manager", payload={"agent_id": str(agent_id)})
        )
        return context

    async def _transition(
        self,
        agent_id: UUID,
        target_state: AgentStatus,
        event_type: type[AgentInitialized]
        | type[AgentStarted]
        | type[AgentPaused]
        | type[AgentResumed]
        | type[AgentCompleted]
        | type[AgentFailed]
        | type[AgentStopped],
    ) -> Agent:
        async with self._lock:
            agent = self._registry.get(agent_id)
            if agent.status is target_state:
                return agent
            self._require_transition(agent, target_state)
            updated_agent = await self._registry.update_status(agent_id, target_state)
            self._contexts[agent_id] = self._contexts[agent_id].with_state(target_state)
        await self._event_bus.publish(
            event_type(source="agent_manager", payload={"agent_id": str(agent_id)})
        )
        return updated_agent

    def _require_transition(self, agent: Agent, target_state: AgentStatus) -> None:
        if target_state not in self._ALLOWED_TRANSITIONS[agent.status]:
            raise AgentLifecycleError(agent.id, agent.status.value, target_state.value)
