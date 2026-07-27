"""Runtime-only context owned by an Agent Manager."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping
from uuid import UUID, uuid4

from backend.app.core.agent_runtime.domain.status import AgentStatus


UNSET = object()


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentContext:
    """Ephemeral execution context; not persistent memory or conversation history."""

    current_state: AgentStatus
    session_id: UUID = field(default_factory=uuid4)
    current_task: str | None = None
    temporary_variables: Mapping[str, object] = field(default_factory=dict)
    runtime_metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.current_state, AgentStatus):
            raise TypeError("Context current_state must be an AgentStatus value.")
        if self.current_task is not None and not isinstance(self.current_task, str):
            raise TypeError("Context current_task must be a string or None.")
        object.__setattr__(self, "temporary_variables", MappingProxyType(dict(self.temporary_variables)))
        object.__setattr__(self, "runtime_metadata", MappingProxyType(dict(self.runtime_metadata)))

    def with_state(self, state: AgentStatus) -> "AgentContext":
        """Return a context snapshot synchronized with an Agent lifecycle state."""
        return replace(self, current_state=state, updated_at=_utc_now())

    def with_updates(
        self,
        *,
        current_task: str | None | object = UNSET,
        temporary_variables: Mapping[str, object] | None = None,
        runtime_metadata: Mapping[str, object] | None = None,
    ) -> "AgentContext":
        """Return a context snapshot with supplied runtime fields merged or replaced."""
        return replace(
            self,
            current_task=self.current_task if current_task is UNSET else current_task,
            temporary_variables=(
                self.temporary_variables
                if temporary_variables is None
                else {**self.temporary_variables, **temporary_variables}
            ),
            runtime_metadata=(
                self.runtime_metadata
                if runtime_metadata is None
                else {**self.runtime_metadata, **runtime_metadata}
            ),
            updated_at=_utc_now(),
        )
