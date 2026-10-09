"""Provider-neutral observable activities for one Agent interaction."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolActivity:
    tool_name: str
    status: str
    result: object | None = None
    error: str | None = None
    duration: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class InteractionSummary:
    interaction_id: UUID = field(default_factory=uuid4)
    tool_activities: tuple[ToolActivity, ...] = ()
