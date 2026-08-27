"""Immutable, API-safe Memory Runtime record."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Mapping
from uuid import UUID, uuid4

from backend.app.core.memory.domain.memory_kind import MemoryKind


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryRecord:
    memory_id: UUID = field(default_factory=uuid4)
    agent_id: UUID
    content: str
    kind: MemoryKind = MemoryKind.NOTE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, object] = field(default_factory=dict)
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Memory content must be a non-empty string.")
        if len(self.content) > 10_000:
            raise ValueError("Memory content must not exceed 10000 characters.")

    def with_updates(self, *, content: str | None = None, kind: MemoryKind | None = None, metadata: Mapping[str, object] | None = None, tags: tuple[str, ...] | None = None) -> "MemoryRecord":
        return replace(self, content=self.content if content is None else content, kind=self.kind if kind is None else kind, metadata=self.metadata if metadata is None else dict(metadata), tags=self.tags if tags is None else tags, updated_at=datetime.now(UTC))
