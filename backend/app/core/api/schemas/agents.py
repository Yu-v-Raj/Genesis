"""Pydantic response models for the read-only Agent Runtime API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.agent_runtime.domain.agent import MAX_INSTRUCTIONS_LENGTH, Agent
from backend.app.core.agent_runtime.domain.context import AgentContext
from backend.app.core.agent_runtime.domain.interaction import InteractionSummary
from backend.app.core.agent_runtime.domain.session import AgentSession, AgentSessionSummary
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.api.schemas.llm import GenerateResponse, ModelRequest, ModelResponse
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMResponse, Message, ToolCall


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
    allowed_tools: list[str]
    instructions: str

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
            allowed_tools=list(agent.allowed_tools),
            instructions=agent.instructions,
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
    allowed_tools: list[str] | None = None
    instructions: str = Field(default="", max_length=MAX_INSTRUCTIONS_LENGTH)
    initialize: bool = Field(
        default=False, description="Initialize the Agent immediately so it is ready to chat."
    )

    def llm_model_domain(self) -> LLMModel | None:
        return None if self.llm_model is None else self.llm_model.to_domain()


class AgentConfigurationUpdateRequest(BaseModel):
    """Partial update of an Agent's model, tool permissions, and instructions.

    Omitted fields are unchanged; ``llm_model: null`` removes the model.
    """

    llm_model: ModelRequest | None = None
    allowed_tools: list[str] | None = None
    instructions: str | None = Field(default=None, max_length=MAX_INSTRUCTIONS_LENGTH)


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
    session_id: UUID | None = Field(
        default=None, description="Continue this session; defaults to the Agent's active session."
    )


class AgentChatResponse(BaseModel):
    agent: AgentResponse
    response: GenerateResponse
    interaction_id: UUID
    session_id: UUID | None
    tool_activities: list["ToolActivityResponse"]

    @classmethod
    def from_domain(cls, agent: Agent, response: LLMResponse, interaction: InteractionSummary) -> "AgentChatResponse":
        return cls(agent=AgentResponse.from_agent(agent), response=GenerateResponse.from_domain(response), interaction_id=interaction.interaction_id, session_id=interaction.session_id, tool_activities=[ToolActivityResponse.from_domain(activity) for activity in interaction.tool_activities])


class ToolActivityResponse(BaseModel):
    tool_name: str
    status: str
    result: object | None
    error: str | None
    duration: float | None

    @classmethod
    def from_domain(cls, activity: object) -> "ToolActivityResponse":
        return cls(**{name: getattr(activity, name) for name in ("tool_name", "status", "result", "error", "duration")})


class SessionMessageResponse(BaseModel):
    """One conversation message with only display-safe tool details.

    Tool-call arguments and provider metadata (such as Gemini thought signatures) stay
    server-side; the UI gets tool names and outcomes.
    """

    role: str
    content: str
    interaction_id: str | None = None
    tool_name: str | None = None
    tool_status: str | None = None
    tool_calls: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, message: Message) -> "SessionMessageResponse":
        metadata = message.metadata
        tool_calls = metadata.get("tool_calls") or ()
        return cls(
            role=message.role.value,
            content=message.content,
            interaction_id=_optional_str(metadata.get("interaction_id")),
            tool_name=_optional_str(metadata.get("tool_name")),
            tool_status=_optional_str(metadata.get("tool_status")),
            tool_calls=[call.name for call in tool_calls if isinstance(call, ToolCall)],
        )


class AgentSessionResponse(BaseModel):
    id: UUID
    agent_id: UUID
    created_at: datetime
    updated_at: datetime
    messages: list[SessionMessageResponse]

    @classmethod
    def from_domain(cls, session: AgentSession) -> "AgentSessionResponse":
        return cls(id=session.id, agent_id=session.agent_id, created_at=session.created_at, updated_at=session.updated_at, messages=[SessionMessageResponse.from_domain(message) for message in session.messages])


class AgentSessionSummaryResponse(BaseModel):
    id: UUID
    agent_id: UUID
    created_at: datetime
    updated_at: datetime
    message_count: int
    title: str | None

    @classmethod
    def from_domain(cls, summary: AgentSessionSummary) -> "AgentSessionSummaryResponse":
        return cls(
            id=summary.id,
            agent_id=summary.agent_id,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            message_count=summary.message_count,
            title=summary.title,
        )


class AgentSessionListResponse(BaseModel):
    """An Agent's sessions, most recently active first; ``active_session_id`` is resumed by default."""

    active_session_id: UUID | None
    sessions: list[AgentSessionSummaryResponse]


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
