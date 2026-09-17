"""Immutable Agent process metadata."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping
from uuid import UUID, uuid4

from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.llm_runtime.domain.models import LLMModel


# This fixed allowlist preserves v0.10B's built-in capabilities for agents that
# predate tool policy while preventing newly registered tools from being exposed
# automatically.
DEFAULT_ALLOWED_TOOLS = ("echo", "calculator", "uuid", "random_number", "delay")


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class Agent:
    """A process-like record for a future Genesis agent execution unit."""

    name: str
    description: str
    type: str
    id: UUID = field(default_factory=uuid4)
    status: AgentStatus = AgentStatus.CREATED
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    metadata: Mapping[str, object] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    llm_model: LLMModel | None = None
    allowed_tools: tuple[str, ...] = DEFAULT_ALLOWED_TOOLS

    def __post_init__(self) -> None:
        """Validate and freeze collection values at the domain boundary."""
        for field_name, value in (
            ("name", self.name),
            ("description", self.description),
            ("type", self.type),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Agent {field_name} must be a non-empty string.")
        if not isinstance(self.status, AgentStatus):
            raise TypeError("Agent status must be an AgentStatus value.")
        if self.created_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Agent timestamps must be timezone-aware.")
        if self.updated_at < self.created_at:
            raise ValueError("Agent updated_at cannot precede created_at.")
        if not all(isinstance(tag, str) and tag.strip() for tag in self.tags):
            raise ValueError("Agent tags must contain non-empty strings.")
        if self.llm_model is not None and not isinstance(self.llm_model, LLMModel):
            raise TypeError("Agent llm_model must be an LLMModel or None.")
        if not all(isinstance(tool_name, str) and tool_name.strip() for tool_name in self.allowed_tools):
            raise ValueError("Agent allowed_tools must contain non-empty strings.")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "allowed_tools", tuple(self.allowed_tools))

    def with_status(self, status: AgentStatus) -> "Agent":
        """Return a new record with an updated lifecycle status."""
        if not isinstance(status, AgentStatus):
            raise TypeError("Agent status must be an AgentStatus value.")
        return replace(self, status=status, updated_at=_utc_now())

    def with_metadata(self, metadata: Mapping[str, object]) -> "Agent":
        """Return a new record with supplied metadata merged into its metadata."""
        return replace(self, metadata={**self.metadata, **metadata}, updated_at=_utc_now())
