"""Tests for the injectable Genesis WebSocket manager."""

import pytest

from backend.app.core.realtime.application.websocket_manager import WebSocketManager


class FakeConnection:
    """Test double for the manager's minimal connection contract."""

    def __init__(self, fail_sends: bool = False) -> None:
        self.accepted = False
        self.messages: list[dict[str, object]] = []
        self.fail_sends = fail_sends

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, object]) -> None:
        if self.fail_sends:
            raise RuntimeError("connection unavailable")
        self.messages.append(data)


@pytest.mark.asyncio
async def test_manager_connects_and_broadcasts_to_all_clients() -> None:
    """Every active client receives the same broadcast message."""
    manager = WebSocketManager()
    first = FakeConnection()
    second = FakeConnection()

    await manager.connect(first)
    await manager.connect(second)
    delivered = await manager.broadcast({"type": "event", "event": {"id": "example"}})

    assert first.accepted and second.accepted
    assert delivered == 2
    assert first.messages[-1] == second.messages[-1]
    assert await manager.active_connections() == 2


@pytest.mark.asyncio
async def test_manager_removes_disconnected_or_failed_clients() -> None:
    """Explicit disconnects and failed broadcasts do not leak clients."""
    manager = WebSocketManager()
    healthy = FakeConnection()
    failed = FakeConnection()

    await manager.connect(healthy)
    await manager.connect(failed)
    failed.fail_sends = True
    assert await manager.broadcast({"type": "event"}) == 1
    assert await manager.active_connections() == 1

    await manager.disconnect(healthy)
    assert await manager.active_connections() == 0


@pytest.mark.asyncio
async def test_manager_removes_client_when_connection_acknowledgement_fails() -> None:
    """A failed initial acknowledgement cannot leave a stale connection behind."""
    manager = WebSocketManager()
    failed = FakeConnection(fail_sends=True)

    with pytest.raises(RuntimeError, match="connection unavailable"):
        await manager.connect(failed)

    assert await manager.active_connections() == 0
