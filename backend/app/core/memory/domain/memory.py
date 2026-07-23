"""Abstract interface implemented by Genesis memory providers."""

from abc import ABC, abstractmethod

from backend.app.core.memory.domain.memory_entry import MemoryEntry


class Memory(ABC):
    """A named asynchronous store for generic memory entries."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider's unique registry name."""

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> None:
        """Store or replace one memory entry."""

    @abstractmethod
    async def retrieve(self, key: str) -> MemoryEntry | None:
        """Retrieve an entry by key when it exists."""
