"""In-process implementation of the Genesis memory provider contract."""

import asyncio

from backend.app.core.memory.domain.memory import Memory
from backend.app.core.memory.domain.memory_entry import MemoryEntry


class InMemoryMemory(Memory):
    """Store memory entries in an in-process dictionary."""

    def __init__(self, name: str = "in_memory") -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Memory provider names must be non-empty strings.")
        self._name = name
        self._entries: dict[str, MemoryEntry] = {}
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        """Return the provider's registry name."""
        return self._name

    async def store(self, entry: MemoryEntry) -> None:
        """Store or replace an entry by key."""
        async with self._lock:
            self._entries[entry.key] = entry

    async def retrieve(self, key: str) -> MemoryEntry | None:
        """Return the entry stored under ``key`` when present."""
        async with self._lock:
            return self._entries.get(key)
