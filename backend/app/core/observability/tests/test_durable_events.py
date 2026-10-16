"""Durable runtime events: filtered, correlated, redacted, bounded, paged and pruned."""

from datetime import timedelta
from uuid import uuid4

import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.application.durable_event_recorder import DurableEventRecorder
from backend.app.core.observability.application.runtime_event_store import InMemoryRuntimeEventStore
from backend.app.core.observability.domain.events import Event
from backend.app.core.observability.domain.runtime_event import (
    MAX_STORED_PAYLOAD_BYTES,
    EventQuery,
    StoredEvent,
    stored_event,
)
from backend.app.core.observability.infrastructure.sqlalchemy_event_store import SqlAlchemyRuntimeEventStore
from backend.app.core.workflow_runtime.domain.models import utc_now


def stores(session_factory):
    return {"memory": InMemoryRuntimeEventStore(), "sql": SqlAlchemyRuntimeEventStore(session_factory)}


def test_correlation_ids_are_extracted_without_confusing_steps_and_tool_tasks() -> None:
    run, task, execution, approval = uuid4(), uuid4(), uuid4(), uuid4()
    step_event = stored_event(Event(event_type="workflow.task.completed", payload={"workflow_id": str(run), "task_id": "load"}))
    task_event = stored_event(Event(event_type="task.completed", payload={"task_id": str(task), "workflow_id": str(run), "workflow_task_id": "load", "execution_id": None}))
    approval_event = stored_event(Event(event_type="approval.consumed", payload={"approval_id": str(approval), "task_id": str(task), "execution_id": str(execution)}))
    model_event = stored_event(Event(event_type="llm.completed", payload={"interaction_id": str(execution), "usage": {"total_tokens": 3}}))

    assert (step_event.workflow_id, step_event.step_id, step_event.tool_task_id) == (run, "load", None)
    assert (task_event.workflow_id, task_event.step_id, task_event.tool_task_id) == (run, "load", task)
    assert (approval_event.approval_id, approval_event.tool_task_id, approval_event.execution_id) == (approval, task, execution)
    assert model_event.interaction_id == execution and model_event.payload["usage"] == {"total_tokens": 3}


def test_payloads_are_redacted_and_bounded() -> None:
    event = stored_event(
        Event(
            event_type="execution.failed",
            payload={"api_key": "abc", "nested": {"password": "hunter2", "note": "sk-abcdefghijklmnopqrstu"}, "session_id": "s-1", "input_tokens": 4},
        )
    )
    assert event.payload == {"api_key": "[redacted]", "nested": {"password": "[redacted]", "note": "[redacted]"}, "session_id": "s-1", "input_tokens": 4}

    huge = stored_event(Event(event_type="execution.failed", payload={"detail": "x" * (MAX_STORED_PAYLOAD_BYTES + 10)}))
    assert huge.payload["truncated"] is True and "detail" not in huge.payload


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_the_recorder_keeps_only_lifecycle_events_and_pages_them(session_factory, kind: str) -> None:
    store = stores(session_factory)[kind]
    recorder = DurableEventRecorder(store)
    bus = EventBus()
    bus.subscribe(recorder.record)
    run = uuid4()
    for event_type in ("log.created", "system.heartbeat", "llm.requested", "service.registered"):
        await bus.publish(Event(event_type=event_type, payload={"workflow_id": str(run)}))
    for index in range(5):
        await bus.publish(Event(event_type="workflow.task.completed", payload={"workflow_id": str(run), "task_id": f"s{index}"}))
    await bus.publish(Event(event_type="tool.rejected", payload={"reason": "tool_disabled"}))
    await bus.publish(Event(event_type="llm.completed", payload={"interaction_id": str(run)}))
    assert recorder.pending == 7
    assert await recorder.flush() and recorder.pending == 0

    everything = await store.page(EventQuery(), before_sequence=None, limit=50)
    assert [e.event_type for e in everything] == ["llm.completed", "tool.rejected", *["workflow.task.completed"] * 5]
    sequences = [e.sequence for e in everything]
    assert sequences == sorted(sequences, reverse=True) and len(set(sequences)) == 7

    first = await store.page(EventQuery(workflow_id=run), before_sequence=None, limit=2)
    rest = await store.page(EventQuery(workflow_id=run), before_sequence=first[-1].sequence, limit=10)
    assert [e.step_id for e in (*first, *rest)] == ["s4", "s3", "s2", "s1", "s0"]
    assert [e.event_type for e in await store.page(EventQuery(event_type="tool."), before_sequence=None, limit=5)] == ["tool.rejected"]
    assert [e.event_type for e in await store.page(EventQuery(execution_id=run), before_sequence=None, limit=5)] == ["llm.completed"]
    assert await store.page(EventQuery(event_type="workflow_"), before_sequence=None, limit=5) == ()  # "_" is not a wildcard


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_old_events_are_pruned_by_age(session_factory, kind: str) -> None:
    store = stores(session_factory)[kind]
    now = utc_now()
    old = StoredEvent(event_id=str(uuid4()), event_type="execution.completed", source="t", occurred_at=now - timedelta(days=40))
    recent = StoredEvent(event_id=str(uuid4()), event_type="execution.completed", source="t", occurred_at=now - timedelta(days=1))
    await store.append((old, recent))

    recorder = DurableEventRecorder(store, retention_days=30)
    assert await recorder.prune() == 1
    assert [e.event_id for e in await store.page(EventQuery(), before_sequence=None, limit=10)] == [recent.event_id]


@pytest.mark.asyncio
async def test_a_retried_batch_is_not_stored_twice(session_factory) -> None:
    store = SqlAlchemyRuntimeEventStore(session_factory)
    event = stored_event(Event(event_type="execution.completed"))
    await store.append((event,))
    await store.append((event,))
    assert len(await store.page(EventQuery(), before_sequence=None, limit=10)) == 1


@pytest.mark.asyncio
async def test_storage_failures_keep_events_pending_and_a_full_queue_drops_the_oldest() -> None:
    class Flaky(InMemoryRuntimeEventStore):
        down = True

        async def append(self, events):
            if self.down:
                raise RuntimeError("database unavailable")
            await super().append(events)

    store = Flaky()
    recorder = DurableEventRecorder(store, max_pending=3)
    for index in range(5):
        recorder.record(Event(event_type="execution.progress", payload={"step": str(index)}))
    assert recorder.pending == 3 and recorder.dropped == 2

    assert await recorder.flush() is False and recorder.pending == 3  # nothing lost on failure
    store.down = False
    assert await recorder.flush() is True and recorder.pending == 0
    kept = await store.page(EventQuery(), before_sequence=None, limit=10)
    assert [e.payload["step"] for e in kept] == ["4", "3", "2"]


@pytest.mark.asyncio
async def test_stop_writes_what_is_pending() -> None:
    store = InMemoryRuntimeEventStore()
    recorder = DurableEventRecorder(store, flush_interval_seconds=3600)
    await recorder.start()
    recorder.record(Event(event_type="execution.completed"))
    await recorder.stop()
    assert len(await store.page(EventQuery(), before_sequence=None, limit=10)) == 1
