"""Pydantic response models for the read-only Agent Runtime API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.status import AgentStatus


class AgentResponse(BaseModel):
    """External representation of immutable Agent Runtime metadata."""

    id: UUID
    name: str
    description: str
    type: str
    status: AgentStatus
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object]
    tags: list[str]

    @classmethod
    def from_agent(cls, agent: Agent) -> "AgentResponse":
        """Create a response model from a Core Agent record."""
        return cls(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            type=agent.type,
            status=agent.status,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            metadata=dict(agent.metadata),
            tags=list(agent.tags),
        )


class AgentListResponse(BaseModel):
    """A collection of Agent Runtime records."""

    agents: list[AgentResponse]


class AgentCountResponse(BaseModel):
    """The number of Agent Runtime records currently registered."""

    count: int
