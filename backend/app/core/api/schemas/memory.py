"""Pydantic contracts for the Memory Runtime API."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from backend.app.core.memory.domain.memory_kind import MemoryKind
from backend.app.core.memory.domain.memory_record import MemoryRecord

class MemoryResponse(BaseModel):
    memory_id: UUID; agent_id: UUID; content: str; kind: MemoryKind; created_at: datetime; updated_at: datetime; metadata: dict[str, object]; tags: list[str]
    @classmethod
    def from_memory(cls, memory: MemoryRecord) -> "MemoryResponse": return cls(memory_id=memory.memory_id, agent_id=memory.agent_id, content=memory.content, kind=memory.kind, created_at=memory.created_at, updated_at=memory.updated_at, metadata=dict(memory.metadata), tags=list(memory.tags))
class MemoryListResponse(BaseModel): memories: list[MemoryResponse]
class MemoryCreateRequest(BaseModel): content: str = Field(min_length=1, max_length=10_000); kind: MemoryKind = MemoryKind.NOTE; metadata: dict[str, object] = Field(default_factory=dict); tags: list[str] = Field(default_factory=list)
class MemoryUpdateRequest(BaseModel): content: str | None = Field(default=None, min_length=1, max_length=10_000); kind: MemoryKind | None = None; metadata: dict[str, object] | None = None; tags: list[str] | None = None
