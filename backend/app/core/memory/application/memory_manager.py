"""Application service for routing memory operations to registered providers."""

from threading import RLock

from backend.app.core.memory.domain.exceptions import (
    DuplicateMemoryProviderError,
    InvalidMemoryProviderNameError,
    MemoryProviderNotFoundError,
)
from backend.app.core.memory.domain.memory import Memory
from backend.app.core.memory.domain.memory_entry import MemoryEntry
from backend.app.core.memory.application.memory_provider import MemoryProvider
from backend.app.core.memory.domain.memory_kind import MemoryKind
from backend.app.core.memory.domain.memory_record import MemoryRecord
from backend.app.core.memory.domain.exceptions import MemoryNotFoundError, MemoryOwnershipError
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import MemoryCreated, MemoryDeleted, MemoryRetrieved, MemoryUpdated


class MemoryManager:
    """Manage named asynchronous memory providers."""

    def __init__(self, provider: MemoryProvider | None = None, event_bus: EventBus | None = None) -> None:
        self._providers: dict[str, Memory] = {}
        self._lock = RLock()
        self._provider = provider
        self._event_bus = event_bus

    async def create_memory(self, *, agent_id, content: str, kind: MemoryKind = MemoryKind.NOTE, metadata: dict[str, object] | None = None, tags: tuple[str, ...] = ()) -> MemoryRecord:
        provider = self._runtime_provider()
        memory = await provider.create(MemoryRecord(agent_id=agent_id, content=content, kind=kind, metadata={} if metadata is None else dict(metadata), tags=tags))
        await self._publish(MemoryCreated, memory)
        return memory

    async def get_memory(self, memory_id, *, agent_id=None) -> MemoryRecord:
        memory = await self._require(memory_id)
        self._ensure_owner(memory, agent_id)
        await self._publish(MemoryRetrieved, memory)
        return memory

    async def list_memories(self, agent_id=None) -> tuple[MemoryRecord, ...]:
        return await self._runtime_provider().list(agent_id)

    async def search_memories(self, agent_id, query: str) -> tuple[MemoryRecord, ...]:
        if not isinstance(query, str) or not query.strip(): raise ValueError("Memory search query must be non-empty.")
        return await self._runtime_provider().search(query, agent_id)

    async def update_memory(self, memory_id, *, agent_id=None, content: str | None = None, kind: MemoryKind | None = None, metadata: dict[str, object] | None = None, tags: tuple[str, ...] | None = None) -> MemoryRecord:
        current = await self._require(memory_id); self._ensure_owner(current, agent_id)
        updated = await self._runtime_provider().update(current.with_updates(content=content, kind=kind, metadata=metadata, tags=tags))
        assert updated is not None
        await self._publish(MemoryUpdated, updated)
        return updated

    async def delete_memory(self, memory_id, *, agent_id=None) -> MemoryRecord:
        current = await self._require(memory_id); self._ensure_owner(current, agent_id)
        deleted = await self._runtime_provider().delete(memory_id)
        assert deleted is not None
        await self._publish(MemoryDeleted, deleted)
        return deleted

    async def count_memories(self, agent_id=None) -> int:
        return await self._runtime_provider().count(agent_id)

    def _runtime_provider(self) -> MemoryProvider:
        if self._provider is None: raise RuntimeError("Memory Runtime provider is not configured.")
        return self._provider

    async def _require(self, memory_id) -> MemoryRecord:
        memory = await self._runtime_provider().get(memory_id)
        if memory is None: raise MemoryNotFoundError(memory_id)
        return memory

    @staticmethod
    def _ensure_owner(memory: MemoryRecord, agent_id: object | None) -> None:
        if agent_id is not None and memory.agent_id != agent_id: raise MemoryOwnershipError(memory.memory_id)

    async def _publish(self, event_type, memory: MemoryRecord) -> None:
        if self._event_bus is not None:
            await self._event_bus.publish(event_type(source="memory_manager", payload={"memory_id": str(memory.memory_id), "agent_id": str(memory.agent_id), "kind": memory.kind.value}))

    async def register(self, provider: Memory) -> None:
        """Register a memory provider under its unique name."""
        if not isinstance(provider, Memory):
            raise TypeError("Registered providers must implement the Memory base class.")
        self._validate_provider_name(provider.name)

        with self._lock:
            if provider.name in self._providers:
                raise DuplicateMemoryProviderError(provider.name)
            self._providers[provider.name] = provider

    async def unregister(self, provider_name: str) -> Memory:
        """Remove and return a registered memory provider."""
        self._validate_provider_name(provider_name)
        with self._lock:
            try:
                return self._providers.pop(provider_name)
            except KeyError as error:
                raise MemoryProviderNotFoundError(provider_name) from error

    async def resolve(self, provider_name: str) -> Memory:
        """Resolve a memory provider by name."""
        self._validate_provider_name(provider_name)
        with self._lock:
            try:
                return self._providers[provider_name]
            except KeyError as error:
                raise MemoryProviderNotFoundError(provider_name) from error

    async def store(self, provider_name: str, entry: MemoryEntry) -> None:
        """Store an entry through a named memory provider."""
        provider = await self.resolve(provider_name)
        await provider.store(entry)

    async def retrieve(self, provider_name: str, key: str) -> MemoryEntry | None:
        """Retrieve an entry through a named memory provider."""
        provider = await self.resolve(provider_name)
        return await provider.retrieve(key)

    async def registered_names(self) -> tuple[str, ...]:
        """Return a snapshot of registered memory provider names."""
        with self._lock:
            return tuple(self._providers)

    @staticmethod
    def _validate_provider_name(provider_name: object) -> None:
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise InvalidMemoryProviderNameError(
                "Memory provider names must be non-empty strings."
            )
