"""In-memory registry for Agent Runtime process metadata."""

from collections.abc import Mapping
from threading import RLock
from uuid import UUID

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.exceptions import (
    AgentNotFoundError,
    DuplicateAgentError,
)
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import (
    AgentMetadataUpdated,
    AgentRegistered,
    AgentRemoved,
    AgentStatusChanged,
)


class AgentRegistry:
    """Maintain thread-safe Agent metadata and publish its lifecycle events."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._agents: dict[UUID, Agent] = {}
        self._lock = RLock()

    async def register(self, agent: Agent) -> Agent:
        """Register an Agent and publish its registration event."""
        if not isinstance(agent, Agent):
            raise TypeError("Registered agents must be Agent instances.")
        with self._lock:
            if agent.id in self._agents:
                raise DuplicateAgentError(agent.id)
            self._agents[agent.id] = agent
        await self._event_bus.publish(
            AgentRegistered(
                source="agent_registry",
                payload={"agent_id": str(agent.id), "name": agent.name, "type": agent.type},
            )
        )
        return agent

    async def unregister(self, agent_id: UUID) -> Agent:
        """Remove an Agent and publish its removal event."""
        with self._lock:
            try:
                agent = self._agents.pop(agent_id)
            except KeyError as error:
                raise AgentNotFoundError(agent_id) from error
        await self._event_bus.publish(
            AgentRemoved(source="agent_registry", payload={"agent_id": str(agent.id)})
        )
        return agent

    def get(self, agent_id: UUID) -> Agent:
        """Return one registered Agent by identifier."""
        with self._lock:
            try:
                return self._agents[agent_id]
            except KeyError as error:
                raise AgentNotFoundError(agent_id) from error

    def list(self) -> tuple[Agent, ...]:
        """Return a snapshot of all registered Agents in registration order."""
        with self._lock:
            return tuple(self._agents.values())

    def exists(self, agent_id: UUID) -> bool:
        """Return whether an Agent identifier is registered."""
        with self._lock:
            return agent_id in self._agents

    def count(self) -> int:
        """Return the number of registered Agents."""
        with self._lock:
            return len(self._agents)

    async def update_status(self, agent_id: UUID, status: AgentStatus) -> Agent:
        """Create and store an Agent status transition, then publish it."""
        with self._lock:
            current_agent = self.get(agent_id)
            if current_agent.status is status:
                return current_agent
            updated_agent = current_agent.with_status(status)
            self._agents[agent_id] = updated_agent
        await self._event_bus.publish(
            AgentStatusChanged(
                source="agent_registry",
                payload={
                    "agent_id": str(agent_id),
                    "previous_status": current_agent.status.value,
                    "status": updated_agent.status.value,
                },
            )
        )
        return updated_agent

    async def update_metadata(self, agent_id: UUID, metadata: Mapping[str, object]) -> Agent:
        """Merge Agent metadata, store the new record, and publish the update."""
        with self._lock:
            current_agent = self.get(agent_id)
            updated_agent = current_agent.with_metadata(metadata)
            self._agents[agent_id] = updated_agent
        await self._event_bus.publish(
            AgentMetadataUpdated(
                source="agent_registry",
                payload={"agent_id": str(agent_id), "metadata": dict(metadata)},
            )
        )
        return updated_agent
