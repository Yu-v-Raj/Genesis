"""WebSocket API adapter for the Genesis real-time event stream."""

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.app.core.api.dependencies.system import get_websocket_manager
from backend.app.core.realtime.application.websocket_manager import WebSocketManager


router = APIRouter(tags=["realtime"])


@router.websocket("/ws/events")
async def event_stream(
    websocket: WebSocket,
    manager: Annotated[WebSocketManager, Depends(get_websocket_manager)],
) -> None:
    """Keep a client connected to the live Genesis event stream."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
