"""Persist the lifecycle subset of the event stream without slowing its publishers.

The Event Bus awaits every handler inline, so ``record`` only filters and enqueues; a
background task writes batches. A failed write is logged and retried with the next batch;
if storage stays unavailable and the bounded queue fills, the oldest pending events are
dropped and counted rather than blocking execution. Old events are pruned by age.
"""

import asyncio
from collections import deque
from datetime import UTC, datetime, timedelta

from backend.app.core.core_services.logging.logger import logger
from backend.app.core.observability.application.runtime_event_store import RuntimeEventStore
from backend.app.core.observability.domain.events import Event
from backend.app.core.observability.domain.runtime_event import StoredEvent, is_durable, stored_event


class DurableEventRecorder:
    def __init__(
        self,
        store: RuntimeEventStore,
        *,
        retention_days: float = 30.0,
        max_pending: int = 10_000,
        batch_size: int = 200,
        flush_interval_seconds: float = 0.5,
        prune_interval_seconds: float = 3600.0,
    ) -> None:
        if retention_days <= 0 or max_pending < 1 or batch_size < 1:
            raise ValueError("Retention, queue size and batch size must be positive.")
        self._store = store
        self._retention = timedelta(days=retention_days)
        self._pending: deque[StoredEvent] = deque()
        self._max_pending = max_pending
        self._batch_size = batch_size
        self._interval = flush_interval_seconds
        self._prune_every = prune_interval_seconds
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self.dropped = 0

    def record(self, event: Event) -> None:
        """Event Bus subscriber: cheap and synchronous, never raises into the publisher."""
        if not is_durable(event.event_type):
            return
        try:
            stored = stored_event(event)
        except Exception as error:  # a malformed payload must never break the publisher
            logger.error("Runtime event could not be prepared", extra={"genesis_context": {"error_type": type(error).__name__}})
            return
        if len(self._pending) >= self._max_pending:
            self._pending.popleft()
            self.dropped += 1
        self._pending.append(stored)
        if len(self._pending) >= self._batch_size:
            self._wake.set()

    async def start(self) -> None:
        await self.prune()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="runtime-event-recorder")

    async def stop(self) -> None:
        """Write what is pending, then stop the background task."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await self.flush()

    async def flush(self) -> bool:
        """Write every pending event now; False if storage refused (they stay pending)."""
        async with self._write_lock:
            while self._pending:
                batch = tuple(self._pending)[: self._batch_size]
                try:
                    await self._store.append(batch)
                except Exception as error:
                    logger.error("Runtime events could not be stored", extra={"genesis_context": {"error_type": type(error).__name__, "pending": len(self._pending)}})
                    return False
                written = {event.event_id for event in batch}
                while self._pending and self._pending[0].event_id in written:
                    self._pending.popleft()  # by identity: events dropped meanwhile aren't counted twice
        return True

    async def prune(self) -> int:
        try:
            return await self._store.prune(datetime.now(UTC) - self._retention)
        except Exception as error:
            logger.error("Old runtime events could not be pruned", extra={"genesis_context": {"error_type": type(error).__name__}})
            return 0

    @property
    def pending(self) -> int:
        return len(self._pending)

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_prune = loop.time() + self._prune_every
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._interval)
            except TimeoutError:
                pass
            self._wake.clear()
            await self.flush()
            if loop.time() >= next_prune:
                await self.prune()
                next_prune = loop.time() + self._prune_every
