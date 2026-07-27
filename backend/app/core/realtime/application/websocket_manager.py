"""Connection management for real-time Genesis clients."""

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol


class WebSocketConnection(Protocol):
    """Minimal connection contract required by the WebSocket manager."""

    async def accept(self) -> None:
        """Accept the pending WebSocket connection."""

    async def send_json(self, data: Mapping[str, object]) -> None:
        """Send a JSON-compatible message to the client."""


class WebSocketManager:
    """Manage connections safely within Genesis's single ASGI event-loop model.

    ``asyncio.Lock`` serializes connection-registry access among concurrent
    coroutines on the application's event loop. This is the correct scope for
    FastAPI WebSocket objects, which must not be sent from other threads.
    Multi-process deployments require a shared broker, not a thread lock.
    """

    def __init__(self) -> None:
        self._connections: dict[int, WebSocketConnection] = {}
        self._lock = asyncio.Lock()

    async def connect(self, connection: WebSocketConnection) -> None:
        """Accept and register a client, then send its connection acknowledgement."""
        await connection.accept()
        async with self._lock:
            self._connections[id(connection)] = connection
        try:
            await connection.send_json(
                {
                    "type": "connected",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        except Exception:
            await self.disconnect(connection)
            raise

    async def disconnect(self, connection: WebSocketConnection) -> None:
        """Remove a client connection if it is still registered."""
        async with self._lock:
            self._connections.pop(id(connection), None)

    async def broadcast(self, message: Mapping[str, object]) -> int:
        """Send a message to every active client and remove failed connections."""
        async with self._lock:
            connections = tuple(self._connections.items())

        results = await asyncio.gather(
            *(connection.send_json(message) for _, connection in connections),
            return_exceptions=True,
        )
        failed_connection_ids = [
            connection_id
            for (connection_id, _), result in zip(connections, results, strict=True)
            if isinstance(result, Exception)
        ]
        if failed_connection_ids:
            async with self._lock:
                for connection_id in failed_connection_ids:
                    self._connections.pop(connection_id, None)
        return len(connections) - len(failed_connection_ids)

    async def active_connections(self) -> int:
        """Return the current number of connected clients."""
        async with self._lock:
            return len(self._connections)
