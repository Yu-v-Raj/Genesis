"""Ephemeral execution state, intentionally separate from Execution metadata."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
from uuid import UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionContext:
    """Runtime-only state used while a single execution is active."""

    execution_id: UUID
    agent_id: UUID
    current_step: str | None = None
    variables: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)
    cancel_requested: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", MappingProxyType(dict(self.variables)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
