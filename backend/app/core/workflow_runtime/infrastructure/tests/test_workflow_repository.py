"""Integration tests for the SQLAlchemy workflow repository (SQLite, and PostgreSQL if set)."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from backend.app.core.core_services.persistence import PersistenceConflictError
from backend.app.core.workflow_runtime.domain.models import (
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTask,
    WorkflowTaskStatus,
)
from backend.app.core.workflow_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyWorkflowRepository


def definition(**overrides: object) -> WorkflowDefinition:
    fields: dict[str, object] = {
        "name": "pipeline",
        "description": "Read, call, store.",
        "metadata": {"owner": "core"},
        "tasks": (
            WorkflowTask(task_id="read", name="Read", configuration={"tool_name": "echo", "tool_arguments": {"message": "doc"}}),
            WorkflowTask(task_id="call", name="Call", configuration={"tool_name": "calculator", "tool_arguments": {"expression": "1+1"}}, dependencies=("read",)),
        ),
    }
    return WorkflowDefinition(**{**fields, **overrides})  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_definitions_are_versioned_and_immutable(session_factory) -> None:
    repository = SqlAlchemyWorkflowRepository(session_factory)
    v1 = await repository.add_definition(definition())
    v2 = await repository.add_definition(definition(definition_id=v1.definition_id, version=2, name="pipeline v2"))

    with pytest.raises(PersistenceConflictError):
        await repository.add_definition(definition(definition_id=v1.definition_id, version=2))

    latest = await repository.get_definition(v1.definition_id)
    first = await repository.get_definition(v1.definition_id, 1)
    assert latest is not None and (latest.version, latest.name) == (2, "pipeline v2")
    assert first is not None and first.name == "pipeline"
    assert [step.dependencies for step in first.tasks] == [(), ("read",)]
    assert [(d.definition_id, d.version) for d in await repository.list_definitions()] == [(v2.definition_id, 2)]


@pytest.mark.asyncio
async def test_run_and_step_state_are_saved_together_with_compare_and_set(session_factory) -> None:
    repository = SqlAlchemyWorkflowRepository(session_factory)
    stored_definition = await repository.add_definition(definition())
    run = await repository.add_run(stored_definition.new_run())
    started = run.with_task(run.tasks[0].with_updates(status=WorkflowTaskStatus.COMPLETED, result={"echo": "doc"}))

    saved = await repository.save_run(run, started.with_updates(status=WorkflowStatus.QUEUED))
    with pytest.raises(PersistenceConflictError):
        await repository.save_run(run, run.with_updates(status=WorkflowStatus.CANCELLED))

    reloaded = await SqlAlchemyWorkflowRepository(session_factory).get_run(run.workflow_id)
    assert reloaded is not None
    assert (reloaded.status, reloaded.version) == (WorkflowStatus.QUEUED, saved.version)
    assert [(t.task_id, t.status, t.result) for t in reloaded.tasks] == [
        ("read", WorkflowTaskStatus.COMPLETED, {"echo": "doc"}),
        ("call", WorkflowTaskStatus.PENDING, None),
    ]
    assert (reloaded.definition_id, reloaded.definition_version) == (stored_definition.definition_id, 1)


@pytest.mark.asyncio
async def test_runs_are_claimed_once_and_leases_expire(session_factory) -> None:
    repository = SqlAlchemyWorkflowRepository(session_factory)
    run = await repository.add_run((await repository.add_definition(definition())).new_run())
    await repository.save_run(run, run.with_updates(status=WorkflowStatus.QUEUED))
    now = datetime.now(UTC)

    claims = await asyncio.gather(*(SqlAlchemyWorkflowRepository(session_factory).claim_next_run(f"w{i}", now + timedelta(seconds=1)) for i in range(4)))

    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1 and winners[0].status is WorkflowStatus.RUNNING
    assert await repository.expired_runs(now) == ()
    assert [r.workflow_id for r in await repository.expired_runs(now + timedelta(seconds=5))] == [run.workflow_id]
    assert not await repository.renew_run_lease(run.workflow_id, "someone-else", now + timedelta(hours=1))


@pytest.mark.asyncio
async def test_deleting_a_run_removes_its_steps(session_factory) -> None:
    repository = SqlAlchemyWorkflowRepository(session_factory)
    run = await repository.add_run((await repository.add_definition(definition())).new_run())

    await repository.delete_run(run.workflow_id)

    assert await repository.get_run(run.workflow_id) is None
    assert await repository.list_runs() == ()
