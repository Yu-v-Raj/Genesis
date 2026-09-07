"""Pydantic response models for the read-only Agent Runtime API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.context import AgentContext
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.api.schemas.llm import GenerateResponse, ModelRequest, ModelResponse
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMResponse


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
    llm_model: ModelResponse | None

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
            llm_model=(None if agent.llm_model is None else ModelResponse.from_domain(agent.llm_model)),
        )


class AgentListResponse(BaseModel):
    """A collection of Agent Runtime records."""

    agents: list[AgentResponse]


class AgentCountResponse(BaseModel):
    """The number of Agent Runtime records currently registered."""

    count: int


class AgentCreateRequest(BaseModel):
    """Input required to create an Agent Runtime record."""

    id: UUID | None = None
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    type: str = Field(min_length=1)
    metadata: dict[str, object] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    llm_model: ModelRequest | None = None

    def llm_model_domain(self) -> LLMModel | None:
        return None if self.llm_model is None else self.llm_model.to_domain()


class AgentMetadataUpdateRequest(BaseModel):
    """Metadata values to merge into an Agent record."""

    metadata: dict[str, object]


class AgentContextResponse(BaseModel):
    """External representation of an Agent's runtime-only context."""

    session_id: UUID
    current_state: AgentStatus
    current_task: str | None
    temporary_variables: dict[str, object]
    runtime_metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_context(cls, context: AgentContext) -> "AgentContextResponse":
        """Create a response model from a Core runtime context."""
        return cls(
            session_id=context.session_id,
            current_state=context.current_state,
            current_task=context.current_task,
            temporary_variables=dict(context.temporary_variables),
            runtime_metadata=dict(context.runtime_metadata),
            created_at=context.created_at,
            updated_at=context.updated_at,
        )


class AgentContextUpdateRequest(BaseModel):
    """Partial update for ephemeral Agent Runtime context fields."""

    current_task: str | None = None
    temporary_variables: dict[str, object] | None = None
    runtime_metadata: dict[str, object] | None = None


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1)


class AgentChatResponse(BaseModel):
    agent: AgentResponse
    response: GenerateResponse

    @classmethod
    def from_domain(cls, agent: Agent, response: LLMResponse) -> "AgentChatResponse":
        return cls(agent=AgentResponse.from_agent(agent), response=GenerateResponse.from_domain(response))
