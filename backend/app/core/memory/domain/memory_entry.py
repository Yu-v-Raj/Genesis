"""Generic data model for entries stored by Genesis memory providers."""

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """A key-addressable memory value with optional generic metadata."""

    key: str
    value: object
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate that the entry has a usable key."""
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("Memory entry keys must be non-empty strings.")
