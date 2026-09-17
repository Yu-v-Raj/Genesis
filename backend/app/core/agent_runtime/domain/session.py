"""Ephemeral provider-neutral conversation state for one reusable Agent."""

from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

from backend.app.core.llm_runtime.domain.models import Message


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentSession:
    """An in-memory ordered conversation owned by one Agent."""

    agent_id: UUID
    id: UUID = field(default_factory=uuid4)
    messages: tuple[Message, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, UUID):
            raise TypeError("Agent session agent_id must be a UUID.")
        if not all(isinstance(message, Message) for message in self.messages):
            raise TypeError("Agent session messages must be LLM Messages.")
        object.__setattr__(self, "messages", tuple(self.messages))

    def with_messages(self, *messages: Message) -> "AgentSession":
        """Return a session with ordered messages appended."""
        return replace(self, messages=(*self.messages, *messages))
