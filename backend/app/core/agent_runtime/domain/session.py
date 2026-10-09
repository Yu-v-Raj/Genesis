"""Provider-neutral conversation state for one reusable Agent."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from backend.app.core.llm_runtime.domain.models import Message, MessageRole


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentSession:
    """An ordered conversation owned by one Agent. An Agent may have many sessions."""

    agent_id: UUID
    id: UUID = field(default_factory=uuid4)
    messages: tuple[Message, ...] = ()
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, UUID):
            raise TypeError("Agent session agent_id must be a UUID.")
        if not all(isinstance(message, Message) for message in self.messages):
            raise TypeError("Agent session messages must be LLM Messages.")
        object.__setattr__(self, "messages", tuple(self.messages))

    def with_messages(self, *messages: Message) -> "AgentSession":
        """Return a session with ordered messages appended."""
        return replace(self, messages=(*self.messages, *messages), updated_at=_utc_now())

    def summary(self) -> "AgentSessionSummary":
        first_user = next((m.content for m in self.messages if m.role is MessageRole.USER), None)
        return AgentSessionSummary(
            id=self.id,
            agent_id=self.agent_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            message_count=len(self.messages),
            title=None if first_user is None else session_title(first_user),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentSessionSummary:
    """Listing view of a session: enough to choose one without loading its messages."""

    id: UUID
    agent_id: UUID
    created_at: datetime
    updated_at: datetime
    message_count: int
    title: str | None


def session_title(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= 80 else f"{line[:77]}…"
