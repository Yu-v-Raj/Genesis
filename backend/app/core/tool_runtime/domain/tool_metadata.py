"""Immutable descriptive metadata for registered Tools."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from backend.app.core.tool_runtime.domain.tool_capability import ToolCapability
from backend.app.core.tool_runtime.domain.tool_permission import ToolPermission


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolMetadata:
    """Immutable Tool declaration exposed by registry and REST APIs."""

    name: str
    description: str
    version: str = "1.0.0"
    capabilities: tuple[ToolCapability, ...] = ()
    permissions: tuple[ToolPermission, ...] = (ToolPermission.NONE,)
    enabled: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Tool name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Tool description must be a non-empty string.")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("Tool version must be a non-empty string.")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "permissions", tuple(self.permissions))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
