"""Lifecycle state and hook contracts for the Genesis runtime."""

from enum import StrEnum
from typing import Protocol, runtime_checkable


class RuntimeState(StrEnum):
    """States in the Genesis runtime lifecycle."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


@runtime_checkable
class LifecycleHook(Protocol):
    """A Core service that participates in runtime startup and shutdown."""

    async def startup(self) -> None:
        """Initialize resources required by the service."""

    async def shutdown(self) -> None:
        """Release resources owned by the service."""
