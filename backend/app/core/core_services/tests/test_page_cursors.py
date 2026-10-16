"""Paging never skips or repeats a record, even when many share one timestamp.

Every paged list (executions, workflow runs, tool history; in memory and in SQL, and
runtime events by sequence) is walked to the end with small pages over records created
in the same microsecond, mixed with records just before and after.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.infrastructure.sqlalchemy_repositories import SqlAlchemyAgentRepository
from backend.app.core.core_services.pagination import (
    PageCursor,
    comes_after,
    decode_cursor,
    encode_cursor,
    next_cursor,
)
from backend.app.core.execution_runtime.application.execution_history import ExecutionHistory
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyExecutionRepository
from backend.app.core.observability.application.runtime_event_store import InMemoryRuntimeEventStore
from backend.app.core.observability.domain.runtime_event import EventQuery, StoredEvent
from backend.app.core.observability.infrastructure.sqlalchemy_event_store import SqlAlchemyRuntimeEventStore
from backend.app.core.tool_runtime.application.task_repository import InMemoryToolTaskRepository, TaskQuery
from backend.app.core.tool_runtime.domain.task import Task
from backend.app.core.tool_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyToolTaskRepository
from backend.app.core.workflow_runtime.application.in_memory_repository import InMemoryWorkflowRepository
from backend.app.core.workflow_runtime.domain.models import WorkflowDefinition, WorkflowTask
from backend.app.core.workflow_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyWorkflowRepository


TIE = datetime(2026, 10, 16, 10, 0, 0, 123456, tzinfo=UTC)
# Seven records in the same microsecond, plus one just before and one just after.
MOMENTS = [TIE - timedelta(microseconds=1), *[TIE] * 7, TIE + timedelta(microseconds=1)]


async def walk(fetch: Callable[[PageCursor | None, int], Awaitable[tuple]], key: Callable, at: Callable, size: int) -> list[UUID]:
    """Follow next cursors (round-tripped through their string form) until the end."""
    seen: list[UUID] = []
    cursor: PageCursor | None = None
    for _ in range(50):
        page = await fetch(cursor, size + 1)
        seen.extend(key(item) for item in page[:size])
        token = next_cursor(page, size, at, key)
        if token is None:
            return seen
        cursor = decode_cursor(token)
    raise AssertionError("paging did not finish")


def expect_each_once(seen: list[UUID], stored: list[tuple[datetime, UUID]]) -> None:
    assert len(seen) == len(set(seen)) == len(stored)  # nothing repeated, nothing skipped
    assert seen == [record_id for _, record_id in sorted(stored, reverse=True)]  # newest first, ties by id


def test_cursors_round_trip_and_accept_a_bare_timestamp() -> None:
    record = uuid4()
    assert decode_cursor(encode_cursor(TIE, record)) == PageCursor(TIE, record)
    assert "+" not in encode_cursor(TIE, record) and " " not in encode_cursor(TIE, record)  # safe in a URL as is
    assert decode_cursor("2026-10-16T10:00:00+00:00") == PageCursor(datetime(2026, 10, 16, 10, tzinfo=UTC))
    for bad in ("", "yesterday", "2026-10-16T10:00:00Z_not-a-uuid"):
        with pytest.raises(ValueError):
            decode_cursor(bad)
    low, high = UUID(int=1), UUID(int=2)
    assert comes_after(TIE, low, PageCursor(TIE, high)) and not comes_after(TIE, high, PageCursor(TIE, high))
    assert not comes_after(TIE, low, PageCursor(TIE))  # a bare time means strictly before it


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [1, 2, 3, 8])
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_tool_history_pages_cover_every_task_once(session_factory, kind: str, size: int) -> None:
    store = InMemoryToolTaskRepository() if kind == "memory" else SqlAlchemyToolTaskRepository(session_factory)
    tasks = [Task(execution_id=None, tool_name="echo", created_at=moment) for moment in MOMENTS]
    for task in tasks:
        await store.save(task)

    seen = await walk(lambda cursor, limit: store.page(TaskQuery(), before=cursor, limit=limit), lambda t: t.task_id, lambda t: t.created_at, size)
    expect_each_once(seen, [(t.created_at, t.task_id) for t in tasks])


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [1, 2, 3, 8])
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_execution_pages_cover_every_execution_once(session_factory, kind: str, size: int) -> None:
    if kind == "memory":
        repository = ExecutionHistory()
        owner = uuid4()
    else:
        repository = SqlAlchemyExecutionRepository(session_factory)
        agent = Agent(name="worker", description="d", type="t")
        await SqlAlchemyAgentRepository(session_factory).add(agent)
        owner = agent.id
    executions = [Execution(agent_id=owner, created_at=moment, updated_at=moment) for moment in MOMENTS]
    for execution in executions:
        await repository.add(execution, detail="created")

    seen = await walk(lambda cursor, limit: repository.list(None, limit, before=cursor), lambda e: e.execution_id, lambda e: e.created_at, size)
    expect_each_once(seen, [(e.created_at, e.execution_id) for e in executions])


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [1, 2, 3, 8])
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_workflow_run_pages_cover_every_run_once(session_factory, kind: str, size: int) -> None:
    repository = InMemoryWorkflowRepository() if kind == "memory" else SqlAlchemyWorkflowRepository(session_factory)
    definition = WorkflowDefinition(name="w", tasks=(WorkflowTask(task_id="a", name="a", configuration={"tool_name": "echo"}),))
    await repository.add_definition(definition)
    runs = []
    for moment in MOMENTS:
        run = definition.new_run()
        runs.append(await repository.add_run(run.with_updates(created_at=moment)))

    seen = await walk(lambda cursor, limit: repository.list_runs(limit, before=cursor), lambda r: r.workflow_id, lambda r: r.created_at, size)
    expect_each_once(seen, [(r.created_at, r.workflow_id) for r in runs])


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sql"])
async def test_runtime_events_with_identical_times_page_by_sequence(session_factory, kind: str) -> None:
    store = InMemoryRuntimeEventStore() if kind == "memory" else SqlAlchemyRuntimeEventStore(session_factory)
    await store.append(tuple(StoredEvent(event_id=str(uuid4()), event_type="execution.progress", source="t", occurred_at=TIE) for _ in range(9)))

    seen: list[int] = []
    before: int | None = None
    while True:
        page = await store.page(EventQuery(), before_sequence=before, limit=2)
        seen.extend(event.sequence for event in page)
        if len(page) < 2:
            break
        before = page[-1].sequence
    assert len(seen) == len(set(seen)) == 9 and seen == sorted(seen, reverse=True)
