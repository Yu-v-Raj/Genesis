"""Event Bus adapter for real-time client broadcast."""

import json

from backend.app.core.observability.domain.events import Event
from backend.app.core.realtime.application.websocket_manager import WebSocketManager


class RealtimeGateway:
    """Forward already-published Core events to connected real-time clients."""

    def __init__(self, websocket_manager: WebSocketManager) -> None:
        self._websocket_manager = websocket_manager

    async def broadcast_event(self, event: Event) -> None:
        """Serialize and broadcast a Core event without changing its semantics."""
        await self._websocket_manager.broadcast(
            {
                "type": "event",
                "event": {
                    "id": event.id,
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type,
                    "source": event.source,
                    "payload": self._json_compatible(event.payload),
                },
            }
        )

    @staticmethod
    def _json_compatible(payload: object) -> object:
        """Convert event payloads to JSON-compatible values for the wire protocol."""
        return json.loads(json.dumps(payload, default=str))
