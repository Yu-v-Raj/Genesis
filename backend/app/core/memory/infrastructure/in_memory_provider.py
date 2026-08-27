"""Bounded deterministic in-memory provider for Memory Runtime."""

import asyncio
from uuid import UUID

from backend.app.core.memory.application.memory_provider import MemoryProvider
from backend.app.core.memory.domain.memory_record import MemoryRecord


class InMemoryProvider(MemoryProvider):
    def __init__(self, capacity: int = 1_000) -> None:
        if capacity < 1: raise ValueError("Memory provider capacity must be positive.")
        self._capacity = capacity
        self._records: dict[UUID, MemoryRecord] = {}
        self._sequence: dict[UUID, int] = {}
        self._next_sequence = 0
        self._lock = asyncio.Lock()

    async def create(self, memory: MemoryRecord) -> MemoryRecord:
        async with self._lock:
            self._records[memory.memory_id] = memory
            self._next_sequence += 1
            self._sequence[memory.memory_id] = self._next_sequence
            while len(self._records) > self._capacity:
                oldest = min(self._records, key=lambda memory_id: self._sequence[memory_id])
                del self._records[oldest]
                del self._sequence[oldest]
            return memory

    async def get(self, memory_id: UUID) -> MemoryRecord | None:
        async with self._lock: return self._records.get(memory_id)

    async def list(self, agent_id: UUID | None = None) -> tuple[MemoryRecord, ...]:
        async with self._lock:
            records = (item for item in self._records.values() if agent_id is None or item.agent_id == agent_id)
            return tuple(sorted(records, key=lambda item: self._sequence[item.memory_id], reverse=True))

    async def search(self, query: str, agent_id: UUID) -> tuple[MemoryRecord, ...]:
        needle = query.casefold()
        return tuple(item for item in await self.list(agent_id) if needle in item.content.casefold() or needle in " ".join(item.tags).casefold() or needle in str(item.metadata).casefold())

    async def update(self, memory: MemoryRecord) -> MemoryRecord | None:
        async with self._lock:
            if memory.memory_id not in self._records: return None
            self._records[memory.memory_id] = memory
            return memory

    async def delete(self, memory_id: UUID) -> MemoryRecord | None:
        async with self._lock:
            memory = self._records.pop(memory_id, None)
            self._sequence.pop(memory_id, None)
            return memory

    async def count(self, agent_id: UUID | None = None) -> int:
        return len(await self.list(agent_id))
