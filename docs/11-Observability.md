# Genesis Observability

## Purpose

Observability is a Core capability that makes Genesis runtime activity inspectable without coupling Core services to FastAPI, a dashboard, or a distributed broker. The current implementation is intentionally in-process: events are dispatched through the Core Event Bus and retained in a bounded in-memory history for the System API.

## Publishing events

Core services publish immutable typed events through an injected `EventBus`:

```python
from backend.app.core.observability.domain.events import ToolRegistered

await event_bus.publish(
    ToolRegistered(source="tool_manager", payload={"tool": tool.name})
)
```

Each event provides a generated `id`, UTC `timestamp`, `event_type`, `source`, and `payload`. Existing string-based publications remain supported for backward compatibility, but new Core code should use the typed event classes in `backend.app.core.observability.domain.events`.

## Subscribing to events

Subscribers are registered against an event type, or against every event when only a handler is provided. Handlers may be synchronous or asynchronous; a failed handler is isolated so it cannot prevent delivery to later subscribers.

```python
def record_tool_event(event: Event) -> None:
    audit_store.append(event)

event_bus.subscribe("tool.registered", record_tool_event)
```

The in-memory `EventHistory` is the default all-event subscriber. It is a circular buffer configured with `EVENT_HISTORY_SIZE` (default: 1000), so the newest event replaces the oldest after capacity is reached.

## Logging

`LoggerService` is an application-scoped, injectable service. Its asynchronous `debug`, `info`, `warning`, `error`, and `critical` methods write structured JSON through Python's standard logging subsystem and then publish a `LogCreated` event.

```python
await logger_service.info(
    "Workflow accepted",
    source="workflow_engine",
    workflow_name=workflow.name,
)
```

The log event payload contains the level, message, and supplied context. This keeps logs queryable through the same event history without making the event system depend on a logging implementation.

## Runtime heartbeat and API

`HeartbeatService` publishes a `Heartbeat` event every `HEARTBEAT_INTERVAL_SECONDS` (default: 30). Each heartbeat includes process uptime and the current runtime state. The FastAPI adapter exposes read-only snapshots:

- `GET /api/events`
- `GET /api/events/latest`
- `GET /api/events/types`
- `GET /api/logs`
- `GET /api/logs/errors`

These endpoints query `EventHistory`; they do not call Core services directly or mutate runtime state.

## Future agents

Future agents, workflow steps, plugins, and tools receive the `EventBus` and `LoggerService` from the Service Registry. They should publish typed lifecycle events at meaningful boundaries and log structured context rather than introducing direct dashboard dependencies. A future persistent event store, message broker, or WebSocket adapter can subscribe to the same bus without requiring changes to producers.
