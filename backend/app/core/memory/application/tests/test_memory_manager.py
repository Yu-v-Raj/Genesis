"""Unit tests for the Genesis Memory Framework."""

import pytest

from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.memory.domain.exceptions import (
    DuplicateMemoryProviderError,
    MemoryProviderNotFoundError,
)
from backend.app.core.memory.domain.memory_entry import MemoryEntry
from backend.app.core.memory.infrastructure.in_memory_memory import InMemoryMemory


@pytest.mark.asyncio
async def test_register_and_resolve_provider() -> None:
    """Registered providers can be resolved by name."""
    manager = MemoryManager()
    provider = InMemoryMemory()

    await manager.register(provider)

    assert await manager.resolve("in_memory") is provider


@pytest.mark.asyncio
async def test_duplicate_provider_registration_raises_exception() -> None:
    """Provider names are unique within one manager."""
    manager = MemoryManager()
    await manager.register(InMemoryMemory())

    with pytest.raises(DuplicateMemoryProviderError, match="in_memory"):
        await manager.register(InMemoryMemory())


@pytest.mark.asyncio
async def test_store_and_retrieve_memory_entry() -> None:
    """Entries are stored and retrieved through the selected provider."""
    manager = MemoryManager()
    await manager.register(InMemoryMemory())
    entry = MemoryEntry(key="greeting", value="Genesis", metadata={"source": "test"})

    await manager.store("in_memory", entry)

    assert await manager.retrieve("in_memory", "greeting") is entry


@pytest.mark.asyncio
async def test_unknown_provider_raises_exception() -> None:
    """Unknown provider names produce a meaningful resolution error."""
    with pytest.raises(MemoryProviderNotFoundError, match="missing_provider"):
        await MemoryManager().resolve("missing_provider")


@pytest.mark.asyncio
async def test_unregister_removes_provider() -> None:
    """Unregistering removes the provider from future resolution."""
    manager = MemoryManager()
    provider = InMemoryMemory()
    await manager.register(provider)

    assert await manager.unregister("in_memory") is provider
    with pytest.raises(MemoryProviderNotFoundError):
        await manager.resolve("in_memory")
