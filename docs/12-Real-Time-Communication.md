# Real-Time Communication

## Purpose

Genesis streams already-published Core events to connected clients without making Core services depend on FastAPI, WebSockets, or the dashboard. REST remains the source of the dashboard's initial state; the real-time stream carries only subsequent changes.

## Backend flow

```text
Core service → EventBus.publish(event) → EventHistory → RealtimeGateway → WebSocketManager → clients
```

`WebSocketManager` is an application-scoped service registered through the Service Registry. It accepts, tracks, broadcasts to, and removes WebSocket clients. `RealtimeGateway` is its Event Bus adapter and is subscribed after event history, preserving the Event Bus as the single producer boundary.

Clients connect to `GET /ws/events` using the WebSocket protocol. A successful connection receives:

```json
{"type": "connected", "timestamp": "2026-07-27T00:00:00+00:00"}
```

Published Core events use this envelope:

```json
{
  "type": "event",
  "event": {
    "id": "...",
    "timestamp": "...",
    "event_type": "system.heartbeat",
    "source": "runtime",
    "payload": {}
  }
}
```

## Frontend flow

```text
WebSocket → RealtimeService → useRealtime() → dashboard components
```

`RealtimeService` owns browser socket creation, exponential-backoff reconnects, and cleanup. Components never open sockets directly. `useSystemDashboard` loads REST data once, then applies incoming events to the dashboard view model for live activity, logs, service state, and heartbeat status.

`useRealtime()` also exposes explicit `connect`, `disconnect`, and `reconnect` controls for future interactive clients. The WebSocket Manager uses `asyncio.Lock` because each FastAPI process owns its WebSocket objects on an ASGI event loop; cross-thread sends are invalid, and cross-process fan-out is a future broker concern rather than a thread-lock concern.

Configure the browser endpoint with `NEXT_PUBLIC_REALTIME_URL`; see `frontend/.env.example`.

## Future use

Agents, tools, plugins, and workflows reuse the layer by publishing typed Core events through their injected Event Bus. They do not need to know whether a dashboard, WebSocket client, persistent audit adapter, or future agent-to-agent transport is subscribed.
