"""Immutable output returned by a Tool invocation."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolResult:
    """Terminal result of one Tool invocation."""

    status: ToolResultStatus
    output: object | None = None
    logs: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    duration: float = 0.0
    error: str | None = None

    def __post_init__(self) -> None:
        if self.duration < 0:
            raise ValueError("Tool result duration cannot be negative.")
        object.__setattr__(self, "logs", tuple(self.logs))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
