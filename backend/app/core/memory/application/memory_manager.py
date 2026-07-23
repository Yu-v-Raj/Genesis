"""Application service for routing memory operations to registered providers."""

from threading import RLock

from backend.app.core.memory.domain.exceptions import (
    DuplicateMemoryProviderError,
    InvalidMemoryProviderNameError,
    MemoryProviderNotFoundError,
)
from backend.app.core.memory.domain.memory import Memory
from backend.app.core.memory.domain.memory_entry import MemoryEntry


class MemoryManager:
    """Manage named asynchronous memory providers."""

    def __init__(self) -> None:
        self._providers: dict[str, Memory] = {}
        self._lock = RLock()

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
