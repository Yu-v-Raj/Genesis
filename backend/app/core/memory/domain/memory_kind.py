"""Small, explicit classifications for agent-owned memories."""

from enum import StrEnum


class MemoryKind(StrEnum):
    FACT = "fact"
    NOTE = "note"
    PREFERENCE = "preference"
    CONTEXT = "context"
