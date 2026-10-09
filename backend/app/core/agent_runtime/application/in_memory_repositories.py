"""Process-local repository adapters: the default when no database is wired in (unit tests,
database-free embeddings). They hold no state across process restarts."""

from collections.abc import Sequence
from uuid import UUID

from backend.app.core.agent_runtime.application.repositories import (
    AgentRepository,
    SessionRepository,
)
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.exceptions import DuplicateAgentError
from backend.app.core.agent_runtime.domain.session import AgentSession, AgentSessionSummary
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.llm_runtime.domain.models import Message


class InMemoryAgentRepository(AgentRepository):
    def __init__(self) -> None:
        self._agents: dict[UUID, Agent] = {}

    async def add(self, agent: Agent) -> None:
        if agent.id in self._agents:
            raise DuplicateAgentError(agent.id)
        self._agents[agent.id] = agent

    async def save(self, agent: Agent) -> None:
        if agent.id not in self._agents:
            raise PersistenceError("The Agent no longer exists in storage.")
        self._agents[agent.id] = agent

    async def delete(self, agent_id: UUID) -> None:
        self._agents.pop(agent_id, None)

    async def list(self) -> tuple[Agent, ...]:
        return tuple(self._agents.values())


class InMemorySessionRepository(SessionRepository):
    def __init__(self) -> None:
        self._sessions: dict[UUID, AgentSession] = {}

    async def create(self, session: AgentSession) -> AgentSession:
        self._sessions[session.id] = session
        return session

    async def get(self, session_id: UUID) -> AgentSession | None:
        return self._sessions.get(session_id)

    async def latest_for_agent(self, agent_id: UUID) -> AgentSession | None:
        owned = [s for s in self._sessions.values() if s.agent_id == agent_id]
        return max(owned, key=lambda s: s.updated_at, default=None)

    async def list_for_agent(self, agent_id: UUID) -> tuple[AgentSessionSummary, ...]:
        owned = [s for s in self._sessions.values() if s.agent_id == agent_id]
        return tuple(s.summary() for s in sorted(owned, key=lambda s: s.updated_at, reverse=True))

    async def append(
        self, session_id: UUID, messages: Sequence[Message], *, expected_length: int
    ) -> AgentSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise PersistenceError("The session no longer exists in storage.")
        if len(session.messages) != expected_length:
            raise PersistenceConflictError("The conversation changed while this message was processed.")
        updated = session.with_messages(*messages)
        self._sessions[session_id] = updated
        return updated

    async def delete_for_agent(self, agent_id: UUID) -> None:
        for session_id in [s.id for s in self._sessions.values() if s.agent_id == agent_id]:
            del self._sessions[session_id]

