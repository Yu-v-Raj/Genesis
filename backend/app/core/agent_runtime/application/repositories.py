"""Persistence ports for Agent definitions and conversation sessions.

Application services depend on these interfaces; SQLAlchemy and in-memory adapters live
in ``agent_runtime.infrastructure``. Implementations raise ``PersistenceError`` (or its
``PersistenceConflictError`` subclass) when storage fails, never driver exceptions.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.session import AgentSession, AgentSessionSummary
from backend.app.core.llm_runtime.domain.models import Message


class AgentRepository(ABC):
    """Durable Agent definitions. Status is stored only as a restoration category."""

    @abstractmethod
    async def add(self, agent: Agent) -> None:
        """Insert a new Agent; raise ``DuplicateAgentError`` if its ID exists."""

    @abstractmethod
    async def save(self, agent: Agent) -> None:
        """Replace an existing Agent's stored definition."""

    @abstractmethod
    async def delete(self, agent_id: UUID) -> None:
        """Delete an Agent and, with it, all of its sessions."""

    @abstractmethod
    async def list(self) -> tuple[Agent, ...]:
        """Return every stored Agent in creation order."""


class SessionRepository(ABC):
    """Durable conversation sessions and their ordered messages."""

    @abstractmethod
    async def create(self, session: AgentSession) -> AgentSession: ...

    @abstractmethod
    async def get(self, session_id: UUID) -> AgentSession | None:
        """Return a session with all of its messages in order."""

    @abstractmethod
    async def latest_for_agent(self, agent_id: UUID) -> AgentSession | None:
        """Return the most recently updated session, which is the one an Agent resumes."""

    @abstractmethod
    async def list_for_agent(self, agent_id: UUID) -> tuple[AgentSessionSummary, ...]:
        """Return session summaries, most recently updated first."""

    @abstractmethod
    async def append(
        self, session_id: UUID, messages: Sequence[Message], *, expected_length: int
    ) -> AgentSession:
        """Atomically append one completed turn.

        ``expected_length`` is the number of messages the caller built the turn on; if the
        stored session has changed since, nothing is written and
        ``PersistenceConflictError`` is raised.
        """

    @abstractmethod
    async def delete_for_agent(self, agent_id: UUID) -> None: ...
