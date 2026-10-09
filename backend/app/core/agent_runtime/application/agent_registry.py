"""Agent registry: durable Agent definitions with a process-local read cache.

Every write goes to the ``AgentRepository`` first and updates the cache only after it
succeeds, so a failed write never leaves the cache ahead of storage. Reads are served
from the cache, which is loaded from the repository at startup (``restore``) and is
authoritative because Genesis runs as a single backend process; a multi-process
deployment would need to read through to the repository instead.
"""

from collections.abc import Mapping
from threading import RLock
from uuid import UUID

from backend.app.core.agent_runtime.application.in_memory_repositories import InMemoryAgentRepository
from backend.app.core.agent_runtime.application.repositories import AgentRepository
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.exceptions import (
    AgentNotFoundError,
    DuplicateAgentError,
)
from backend.app.core.agent_runtime.domain.status import AgentStatus, restoration_status
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import (
    AgentConfigurationUpdated,
    AgentMetadataUpdated,
    AgentRegistered,
    AgentRemoved,
    AgentStatusChanged,
)


class AgentRegistry:
    """Maintain Agent records, persist their definitions, and publish their events."""

    def __init__(self, event_bus: EventBus, repository: AgentRepository | None = None) -> None:
        self._event_bus = event_bus
        self._repository = repository or InMemoryAgentRepository()
        self._agents: dict[UUID, Agent] = {}
        self._lock = RLock()

    async def register(self, agent: Agent) -> Agent:
        """Persist a new Agent and publish its registration event."""
        if not isinstance(agent, Agent):
            raise TypeError("Registered agents must be Agent instances.")
        if self.exists(agent.id):
            raise DuplicateAgentError(agent.id)
        await self._repository.add(agent)
        with self._lock:
            self._agents[agent.id] = agent
        await self._event_bus.publish(
            AgentRegistered(
                source="agent_registry",
                payload={"agent_id": str(agent.id), "name": agent.name, "type": agent.type},
            )
        )
        return agent

    async def unregister(self, agent_id: UUID) -> Agent:
        """Delete an Agent (and its stored sessions) and publish its removal event."""
        agent = self.get(agent_id)
        await self._repository.delete(agent_id)
        with self._lock:
            self._agents.pop(agent_id, None)
        await self._event_bus.publish(
            AgentRemoved(source="agent_registry", payload={"agent_id": str(agent.id)})
        )
        return agent

    async def stored_agents(self) -> tuple[Agent, ...]:
        """Read every stored Agent definition, bypassing the cache."""
        return await self._repository.list()

    def restore(self, agent: Agent) -> None:
        """Place a stored Agent in the cache without re-persisting it or publishing events."""
        with self._lock:
            self._agents[agent.id] = agent

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

    async def update_status(
        self, agent_id: UUID, status: AgentStatus, *, interaction_id: UUID | None = None
    ) -> Agent:
        """Apply a status transition, persisting it only when its restoration category changes.

        Per-turn IDLE <-> RUNNING flips are therefore not written to storage: a crash
        mid-turn restores the Agent as available, never as RUNNING.
        """
        current_agent = self.get(agent_id)
        if current_agent.status is status:
            return current_agent
        updated_agent = current_agent.with_status(status)
        if restoration_status(current_agent.status) is not restoration_status(status):
            await self._repository.save(updated_agent)
        with self._lock:
            self._agents[agent_id] = updated_agent
        await self._event_bus.publish(
            AgentStatusChanged(
                source="agent_registry",
                payload={
                    "agent_id": str(agent_id),
                    "previous_status": current_agent.status.value,
                    "status": updated_agent.status.value,
                    **({} if interaction_id is None else {"interaction_id": str(interaction_id)}),
                },
            )
        )
        return updated_agent

    async def update_configuration(self, agent: Agent) -> Agent:
        """Persist a reconfigured Agent record and publish which fields changed."""
        current_agent = self.get(agent.id)
        await self._repository.save(agent)
        with self._lock:
            self._agents[agent.id] = agent
        changed = [
            name
            for name in ("llm_model", "allowed_tools", "instructions")
            if getattr(current_agent, name) != getattr(agent, name)
        ]
        # Instructions are user-authored prompt text, so events carry field names only.
        await self._event_bus.publish(
            AgentConfigurationUpdated(
                source="agent_registry",
                payload={"agent_id": str(agent.id), "changed": changed},
            )
        )
        return agent

    async def update_metadata(self, agent_id: UUID, metadata: Mapping[str, object]) -> Agent:
        """Merge and persist Agent metadata, then publish the update."""
        updated_agent = self.get(agent_id).with_metadata(metadata)
        await self._repository.save(updated_agent)
        with self._lock:
            self._agents[agent_id] = updated_agent
        await self._event_bus.publish(
            AgentMetadataUpdated(
                source="agent_registry",
                payload={"agent_id": str(agent_id), "metadata": dict(metadata)},
            )
        )
        return updated_agent
