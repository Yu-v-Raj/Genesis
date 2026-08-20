"""Immutable input submitted to Tool Runtime."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
from uuid import UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolRequest:
    """One request to invoke a named Tool for an Execution task."""

    tool_name: str
    execution_id: UUID | None = None
    task_id: UUID | None = None
    arguments: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("Tool request name must be a non-empty string.")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
