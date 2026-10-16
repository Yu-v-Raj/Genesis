"""SQLAlchemy adapter for the tool task repository port."""

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.core_services.pagination import PageCursor, after_cursor
from backend.app.core.tool_runtime.application.task_repository import TaskQuery, ToolTaskRepository
from backend.app.core.tool_runtime.domain.task import Task, TaskStatus
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus
from backend.app.core.tool_runtime.infrastructure.orm import ToolTaskRow
from backend.app.database.transactions import persistence_transaction


MAX_STORED_OUTPUT_BYTES = 16 * 1024
OUTPUT_PREVIEW_CHARACTERS = 2_000
MAX_STORED_ERROR_CHARACTERS = 4_000
MAX_STORED_LOGS = 50
MAX_STORED_LOG_CHARACTERS = 500


class SqlAlchemyToolTaskRepository(ToolTaskRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def save(self, task: Task) -> None:
        columns = _columns(task)
        async with persistence_transaction(self._factory, "tool_task.save") as db:
            result = await db.execute(update(ToolTaskRow).where(ToolTaskRow.id == task.task_id).values(**columns))
            if result.rowcount == 0:
                await db.execute(insert(ToolTaskRow).values(id=task.task_id, **columns))

    async def get(self, task_id: UUID) -> Task | None:
        async with persistence_transaction(self._factory, "tool_task.get") as db:
            row = await db.get(ToolTaskRow, task_id)
            return None if row is None else _from_row(row)

    async def page(self, query: TaskQuery, *, before: PageCursor | None, limit: int) -> tuple[Task, ...]:
        statement = select(ToolTaskRow).order_by(ToolTaskRow.created_at.desc(), ToolTaskRow.id.desc()).limit(limit)
        if before is not None:
            statement = statement.where(after_cursor(ToolTaskRow.created_at, ToolTaskRow.id, before))
        if query.execution_id is not None:
            statement = statement.where(ToolTaskRow.execution_id == query.execution_id)
        if query.workflow_id is not None:
            statement = statement.where(ToolTaskRow.workflow_id == query.workflow_id)
        if query.approval_id is not None:
            statement = statement.where(ToolTaskRow.approval_id == query.approval_id)
        if query.tool_name is not None:
            statement = statement.where(ToolTaskRow.tool_name == query.tool_name)
        async with persistence_transaction(self._factory, "tool_task.page") as db:
            return tuple(_from_row(row) for row in (await db.scalars(statement)).all())

    async def unfinished(self) -> tuple[Task, ...]:
        async with persistence_transaction(self._factory, "tool_task.unfinished") as db:
            rows = (
                await db.scalars(select(ToolTaskRow).where(ToolTaskRow.status.in_((TaskStatus.PENDING.value, TaskStatus.RUNNING.value))))
            ).all()
            return tuple(_from_row(row) for row in rows)


def bounded_output(output: object) -> object:
    """The output itself when small; otherwise a marked preview (never silently cut)."""
    try:
        encoded = json.dumps(output, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        encoded = json.dumps(str(output), ensure_ascii=False)
        output = str(output)
    if len(encoded.encode()) <= MAX_STORED_OUTPUT_BYTES:
        return output
    return {"truncated": True, "bytes": len(encoded.encode()), "preview": encoded[:OUTPUT_PREVIEW_CHARACTERS]}


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value is not None else None
    except ValueError:
        return None


def _int(value: object) -> int | None:
    try:
        return int(str(value)) if value is not None else None
    except ValueError:
        return None


def _columns(task: Task) -> dict[str, object]:
    meta = task.metadata
    result = task.result
    return {
        "tool_name": task.tool_name,
        "tool_version": task.tool_version,
        "status": task.status.value,
        "caller": meta.get("caller") if isinstance(meta.get("caller"), str) else None,
        "execution_id": task.execution_id,
        "agent_id": _uuid(meta.get("agent_id")),
        "interaction_id": _uuid(meta.get("interaction_id")),
        "workflow_id": _uuid(meta.get("workflow_id")),
        "workflow_task_id": meta.get("workflow_task_id") if isinstance(meta.get("workflow_task_id"), str) else None,
        "workflow_attempt": _int(meta.get("workflow_attempt")),
        "approval_id": _uuid(meta.get("approval_id")),
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "arguments": dict(task.arguments),
        "task_metadata": json.loads(json.dumps(dict(meta), default=str)),
        "result_status": None if result is None else result.status.value,
        "result_output": None if result is None or result.output is None else bounded_output(result.output),
        "result_error": None if result is None or result.error is None else result.error[:MAX_STORED_ERROR_CHARACTERS],
        "result_metadata": None if result is None else json.loads(json.dumps(dict(result.metadata), default=str)),
        "result_logs": None if result is None else [line[:MAX_STORED_LOG_CHARACTERS] for line in result.logs[:MAX_STORED_LOGS]],
        "result_duration": None if result is None else result.duration,
    }


def _from_row(row: ToolTaskRow) -> Task:
    result = None
    if row.result_status is not None:
        result = ToolResult(
            status=ToolResultStatus(row.result_status),
            output=row.result_output,
            logs=tuple(row.result_logs or ()),
            metadata=dict(row.result_metadata or {}),
            duration=max(row.result_duration or 0.0, 0.0),
            error=row.result_error,
        )
    return Task(
        task_id=row.id,
        execution_id=row.execution_id,
        tool_name=row.tool_name,
        status=TaskStatus(row.status),
        created_at=_aware(row.created_at),
        started_at=None if row.started_at is None else _aware(row.started_at),
        finished_at=None if row.finished_at is None else _aware(row.finished_at),
        metadata=dict(row.task_metadata or {}),
        result=result,
        tool_version=row.tool_version,
        arguments=dict(row.arguments or {}),
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
