"""Periodic runtime heartbeat publication."""

import asyncio
from collections.abc import Callable

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import Heartbeat


class HeartbeatService:
    """Publish runtime heartbeat events until explicitly stopped."""

    def __init__(
        self,
        event_bus: EventBus,
        runtime_state: Callable[[], str],
        uptime: Callable[[], float],
        interval_seconds: float = 30.0,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("Heartbeat interval must be greater than zero.")
        self._event_bus = event_bus
        self._runtime_state = runtime_state
        self._uptime = uptime
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start publishing heartbeat events if not already running."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="genesis-heartbeat")

    async def stop(self) -> None:
        """Stop the background heartbeat task gracefully."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def publish_once(self) -> None:
        """Publish one heartbeat with current uptime and runtime state."""
        await self._event_bus.publish(
            Heartbeat(
                source="runtime",
                payload={
                    "uptime": self._uptime(),
                    "runtime_state": self._runtime_state(),
                },
            )
        )

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            await self.publish_once()
