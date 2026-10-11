"""SQLAlchemy adapter for the workflow repository port."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.workflow_runtime.application.repositories import WorkflowRepository
from backend.app.core.workflow_runtime.domain.models import (
    Workflow,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTask,
    WorkflowTaskStatus,
)
from backend.app.core.workflow_runtime.infrastructure.orm import (
    WorkflowDefinitionRow,
    WorkflowRunRow,
    WorkflowRunStepRow,
)
from backend.app.database.transactions import persistence_transaction


_LEASED = (WorkflowStatus.RUNNING.value, WorkflowStatus.PAUSED.value)


class SqlAlchemyWorkflowRepository(WorkflowRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    # ---------------------------------------------------------------- definitions

    async def add_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        try:
            async with persistence_transaction(self._factory, "workflow.definition.add") as db:
                await db.execute(
                    insert(WorkflowDefinitionRow).values(
                        id=definition.definition_id,
                        version=definition.version,
                        name=definition.name,
                        description=definition.description,
                        definition_metadata=dict(definition.metadata),
                        steps=[_step_definition(task) for task in definition.tasks],
                        created_at=definition.created_at,
                    )
                )
        except PersistenceError as error:
            if isinstance(error.__cause__, IntegrityError):
                raise PersistenceConflictError("That workflow definition version already exists.") from error.__cause__
            raise
        return definition

    async def get_definition(self, definition_id: UUID, version: int | None = None) -> WorkflowDefinition | None:
        query = select(WorkflowDefinitionRow).where(WorkflowDefinitionRow.id == definition_id)
        query = query.where(WorkflowDefinitionRow.version == version) if version is not None else query.order_by(WorkflowDefinitionRow.version.desc()).limit(1)
        async with persistence_transaction(self._factory, "workflow.definition.get") as db:
            row = await db.scalar(query)
        return None if row is None else _definition_from_row(row)

    async def list_definitions(self) -> tuple[WorkflowDefinition, ...]:
        latest = (
            select(WorkflowDefinitionRow.id, func.max(WorkflowDefinitionRow.version).label("version"))
            .group_by(WorkflowDefinitionRow.id)
            .subquery()
        )
        query = (
            select(WorkflowDefinitionRow)
            .join(latest, (WorkflowDefinitionRow.id == latest.c.id) & (WorkflowDefinitionRow.version == latest.c.version))
            .order_by(WorkflowDefinitionRow.created_at.desc())
        )
        async with persistence_transaction(self._factory, "workflow.definition.list") as db:
            return tuple(_definition_from_row(row) for row in (await db.scalars(query)).all())

    # ----------------------------------------------------------------------- runs

    async def add_run(self, run: Workflow) -> Workflow:
        stored = replace(run, version=1)
        async with persistence_transaction(self._factory, "workflow.run.add") as db:
            await db.execute(insert(WorkflowRunRow).values(**_run_columns(stored)))
            await db.execute(insert(WorkflowRunStepRow), [_step_columns(stored.workflow_id, i, t) for i, t in enumerate(stored.tasks)])
        return stored

    async def save_run(self, current: Workflow, updated: Workflow) -> Workflow:
        saved = replace(updated, version=current.version + 1)
        async with persistence_transaction(self._factory, "workflow.run.save") as db:
            result = await db.execute(
                update(WorkflowRunRow)
                .where(WorkflowRunRow.id == current.workflow_id, WorkflowRunRow.version == current.version)
                .values(**_run_columns(saved))
            )
            if result.rowcount != 1:
                if await db.get(WorkflowRunRow, current.workflow_id) is None:
                    raise PersistenceError("The workflow run no longer exists in storage.")
                raise PersistenceConflictError("The workflow run changed concurrently.")
            before = {task.task_id: task for task in current.tasks}
            for position, task in enumerate(saved.tasks):
                if before.get(task.task_id) != task:
                    columns = _step_columns(saved.workflow_id, position, task)
                    await db.execute(
                        update(WorkflowRunStepRow)
                        .where(WorkflowRunStepRow.run_id == saved.workflow_id, WorkflowRunStepRow.task_id == task.task_id)
                        .values(**{k: v for k, v in columns.items() if k not in {"run_id", "task_id"}})
                    )
        return saved

    async def get_run(self, run_id: UUID) -> Workflow | None:
        async with persistence_transaction(self._factory, "workflow.run.get") as db:
            row = await db.get(WorkflowRunRow, run_id)
            if row is None:
                return None
            steps = await _steps(db, [run_id])
        return _run_from_row(row, steps.get(run_id, []))

    async def list_runs(self, limit: int = 200) -> tuple[Workflow, ...]:
        return await self._runs(select(WorkflowRunRow).order_by(WorkflowRunRow.created_at.desc()).limit(limit), "workflow.run.list")

    async def delete_run(self, run_id: UUID) -> None:
        async with persistence_transaction(self._factory, "workflow.run.delete") as db:
            await db.execute(delete(WorkflowRunRow).where(WorkflowRunRow.id == run_id))

    async def claim_next_run(self, owner: str, lease_expires_at: datetime) -> Workflow | None:
        for _ in range(5):
            async with persistence_transaction(self._factory, "workflow.run.claim") as db:
                row = await db.scalar(
                    select(WorkflowRunRow)
                    .where(WorkflowRunRow.status == WorkflowStatus.QUEUED.value)
                    .order_by(WorkflowRunRow.updated_at)
                    .limit(1)
                )
                if row is None:
                    return None
                result = await db.execute(
                    update(WorkflowRunRow)
                    .where(
                        WorkflowRunRow.id == row.id,
                        WorkflowRunRow.version == row.version,
                        WorkflowRunRow.status == WorkflowStatus.QUEUED.value,
                    )
                    .values(
                        status=WorkflowStatus.RUNNING.value,
                        lease_owner=owner,
                        lease_expires_at=lease_expires_at,
                        updated_at=datetime.now(UTC),
                        version=row.version + 1,
                    )
                )
                if result.rowcount == 1:
                    run_id = row.id
                    break
        else:
            return None
        return await self.get_run(run_id)

    async def renew_run_lease(self, run_id: UUID, owner: str, lease_expires_at: datetime) -> bool:
        async with persistence_transaction(self._factory, "workflow.run.renew_lease") as db:
            result = await db.execute(
                update(WorkflowRunRow)
                .where(WorkflowRunRow.id == run_id, WorkflowRunRow.lease_owner == owner, WorkflowRunRow.status.in_(_LEASED))
                .values(lease_expires_at=lease_expires_at)
            )
        return result.rowcount == 1

    async def expired_runs(self, now: datetime) -> tuple[Workflow, ...]:
        return await self._runs(
            select(WorkflowRunRow).where(
                WorkflowRunRow.status.in_(_LEASED),
                (WorkflowRunRow.lease_expires_at.is_(None)) | (WorkflowRunRow.lease_expires_at < now),
            ),
            "workflow.run.expired",
        )

    async def _runs(self, query, operation: str) -> tuple[Workflow, ...]:  # type: ignore[no-untyped-def]
        async with persistence_transaction(self._factory, operation) as db:
            rows = (await db.scalars(query)).all()
            steps = await _steps(db, [row.id for row in rows])
        return tuple(_run_from_row(row, steps.get(row.id, [])) for row in rows)


async def _steps(db: AsyncSession, run_ids: Sequence[UUID]) -> dict[UUID, list[WorkflowRunStepRow]]:
    if not run_ids:
        return {}
    rows = (
        await db.scalars(
            select(WorkflowRunStepRow).where(WorkflowRunStepRow.run_id.in_(run_ids)).order_by(WorkflowRunStepRow.position)
        )
    ).all()
    grouped: dict[UUID, list[WorkflowRunStepRow]] = {}
    for row in rows:
        grouped.setdefault(row.run_id, []).append(row)
    return grouped


def _step_definition(task: WorkflowTask) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "name": task.name,
        "action": task.action,
        "configuration": dict(task.configuration),
        "dependencies": list(task.dependencies),
        "metadata": dict(task.metadata),
    }


def _definition_from_row(row: WorkflowDefinitionRow) -> WorkflowDefinition:
    return WorkflowDefinition(
        definition_id=row.id,
        version=row.version,
        name=row.name,
        description=row.description,
        metadata=row.definition_metadata or {},
        created_at=_aware(row.created_at),
        tasks=tuple(
            WorkflowTask(
                task_id=str(step["task_id"]),
                name=str(step["name"]),
                action=str(step.get("action", "tool")),
                configuration=dict(step.get("configuration") or {}),  # type: ignore[arg-type]
                dependencies=tuple(step.get("dependencies") or ()),  # type: ignore[arg-type]
                metadata=dict(step.get("metadata") or {}),  # type: ignore[arg-type]
            )
            for step in row.steps
        ),
    )


def _run_columns(run: Workflow) -> dict[str, object]:
    return {
        "id": run.workflow_id,
        "definition_id": run.definition_id,
        "definition_version": run.definition_version,
        "name": run.name,
        "description": run.description,
        "status": run.status.value,
        "attempt": run.attempt,
        "run_metadata": dict(run.metadata),
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "lease_owner": run.lease_owner,
        "lease_expires_at": run.lease_expires_at,
        "version": run.version,
    }


def _step_columns(run_id: UUID, position: int, task: WorkflowTask) -> dict[str, object]:
    return {
        "run_id": run_id,
        "task_id": task.task_id,
        "position": position,
        "name": task.name,
        "action": task.action,
        "configuration": dict(task.configuration),
        "dependencies": list(task.dependencies),
        "status": task.status.value,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "result": task.result,
        "error": task.error,
        "step_metadata": dict(task.metadata),
    }


def _run_from_row(row: WorkflowRunRow, steps: Sequence[WorkflowRunStepRow]) -> Workflow:
    return Workflow(
        workflow_id=row.id,
        definition_id=row.definition_id,
        definition_version=row.definition_version,
        name=row.name,
        description=row.description,
        status=WorkflowStatus(row.status),
        attempt=row.attempt,
        metadata=row.run_metadata or {},
        error=row.error,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
        lease_owner=row.lease_owner,
        lease_expires_at=None if row.lease_expires_at is None else _aware(row.lease_expires_at),
        version=row.version,
        tasks=tuple(
            WorkflowTask(
                task_id=step.task_id,
                workflow_id=row.id,
                name=step.name,
                action=step.action,
                configuration=step.configuration or {},
                dependencies=tuple(step.dependencies or ()),
                status=WorkflowTaskStatus(step.status),
                created_at=_aware(step.created_at),
                started_at=None if step.started_at is None else _aware(step.started_at),
                finished_at=None if step.finished_at is None else _aware(step.finished_at),
                result=step.result,
                error=step.error,
                metadata=step.step_metadata or {},
            )
            for step in steps
        ),
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
