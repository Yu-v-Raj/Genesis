"""Unit tests for the Genesis runtime lifecycle manager."""

import pytest

from backend.app.core.core_services.service_registry import ServiceRegistry
from backend.app.core.runtime.application.lifecycle_manager import RuntimeLifecycleManager
from backend.app.core.runtime.domain.exceptions import InvalidRuntimeStateError
from backend.app.core.runtime.domain.lifecycle import RuntimeState


class RecordingHook:
    """Lifecycle hook that records the order of lifecycle operations."""

    def __init__(self, events: list[str], name: str) -> None:
        self._events = events
        self._name = name

    async def startup(self) -> None:
        """Record service startup."""
        self._events.append(f"start:{self._name}")

    async def shutdown(self) -> None:
        """Record service shutdown."""
        self._events.append(f"stop:{self._name}")


def test_runtime_starts_in_created_state() -> None:
    """A newly constructed manager has not started the runtime."""
    manager = RuntimeLifecycleManager(ServiceRegistry())

    assert manager.state is RuntimeState.CREATED


@pytest.mark.asyncio
async def test_startup_resolves_registered_hooks() -> None:
    """Startup resolves hooks through the service registry and invokes them."""
    events: list[str] = []
    registry = ServiceRegistry()
    registry.register_singleton("memory", RecordingHook(events, "memory"))
    manager = RuntimeLifecycleManager(registry)
    manager.register_hook("memory")

    await manager.startup()

    assert manager.state is RuntimeState.RUNNING
    assert events == ["start:memory"]


@pytest.mark.asyncio
async def test_shutdown_runs_hooks_in_reverse_order() -> None:
    """Shutdown releases registered services in reverse startup order."""
    events: list[str] = []
    registry = ServiceRegistry()
    registry.register_singleton("memory", RecordingHook(events, "memory"))
    registry.register_singleton("tools", RecordingHook(events, "tools"))
    manager = RuntimeLifecycleManager(registry)
    manager.register_hook("memory")
    manager.register_hook("tools")
    await manager.startup()

    await manager.shutdown()

    assert manager.state is RuntimeState.STOPPED
    assert events == ["start:memory", "start:tools", "stop:tools", "stop:memory"]


@pytest.mark.asyncio
async def test_invalid_state_transitions_raise_meaningful_errors() -> None:
    """Shutdown cannot run before the runtime has started."""
    manager = RuntimeLifecycleManager(ServiceRegistry())

    with pytest.raises(InvalidRuntimeStateError, match="shut down"):
        await manager.shutdown()


@pytest.mark.asyncio
async def test_multiple_startup_attempts_are_rejected() -> None:
    """The runtime can only start once."""
    manager = RuntimeLifecycleManager(ServiceRegistry())
    await manager.startup()

    with pytest.raises(InvalidRuntimeStateError, match="start"):
        await manager.startup()


@pytest.mark.asyncio
async def test_multiple_shutdown_attempts_are_rejected() -> None:
    """The runtime can only shut down once after it is running."""
    manager = RuntimeLifecycleManager(ServiceRegistry())
    await manager.startup()
    await manager.shutdown()

    with pytest.raises(InvalidRuntimeStateError, match="shut down"):
        await manager.shutdown()
