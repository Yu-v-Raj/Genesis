"""Integration tests for the SQLAlchemy execution repository (SQLite, and PostgreSQL if set)."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.infrastructure.sqlalchemy_repositories import SqlAlchemyAgentRepository
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_result import ExecutionResult
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus as S
from backend.app.core.execution_runtime.infrastructure.sqlalchemy_repository import SqlAlchemyExecutionRepository


async def agent_id(factory) -> object:
    agent = Agent(name="worker", description="d", type="t")
    await SqlAlchemyAgentRepository(factory).add(agent)
    return agent.id


async def queued(repository: SqlAlchemyExecutionRepository, owner_agent, **metadata: object) -> Execution:
    created = await repository.add(Execution(agent_id=owner_agent, metadata=metadata), detail="created")
    return await repository.transition(created, created.with_status(S.QUEUED), detail="queued")


@pytest.mark.asyncio
async def test_transitions_are_compare_and_set_and_build_a_timeline(session_factory) -> None:
    repository = SqlAlchemyExecutionRepository(session_factory)
    execution = await queued(repository, await agent_id(session_factory), tool_name="calculator")

    stale = replace(execution, version=1)  # a writer that read before the QUEUED transition
    with pytest.raises(PersistenceConflictError):
        await repository.transition(stale, stale.with_status(S.CANCELLED))

    done = await repository.transition(
        execution,
        execution.with_status(S.FAILED, result=ExecutionResult(status=S.FAILED, output=None, duration=0.5), error="boom", error_category="tool_failed"),
        detail="failed",
    )
    stored = await repository.get(execution.execution_id)
    assert stored is not None
    assert (stored.status, stored.error, stored.error_category, stored.version) == (S.FAILED, "boom", "tool_failed", 3)
    assert stored.result is not None and stored.result.duration == 0.5
    assert dict(stored.metadata) == {"tool_name": "calculator"}
    assert done.version == 3
    timeline = await repository.history(execution.execution_id)
    assert [(t.sequence, t.from_status, t.to_status, t.detail) for t in timeline] == [
        (1, None, S.PENDING, "created"),
        (2, S.PENDING, S.QUEUED, "queued"),
        (3, S.QUEUED, S.FAILED, "failed"),
    ]


@pytest.mark.asyncio
async def test_only_one_worker_can_claim_an_execution(session_factory) -> None:
    repository = SqlAlchemyExecutionRepository(session_factory)
    execution = await queued(repository, await agent_id(session_factory))
    until = datetime.now(UTC) + timedelta(seconds=30)

    claims = await asyncio.gather(
        *(SqlAlchemyExecutionRepository(session_factory).claim_next(f"worker-{i}", until) for i in range(4))
    )

    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    assert winners[0].execution_id == execution.execution_id
    assert winners[0].status is S.STARTING
    assert await repository.claim_next("late", until) is None


@pytest.mark.asyncio
async def test_leases_are_owned_renewed_and_expire(session_factory) -> None:
    repository = SqlAlchemyExecutionRepository(session_factory)
    await queued(repository, await agent_id(session_factory))
    now = datetime.now(UTC)
    claimed = await repository.claim_next("worker-a", now + timedelta(seconds=1))
    assert claimed is not None

    assert not await repository.renew_lease(claimed.execution_id, "worker-b", now + timedelta(hours=1))
    assert await repository.renew_lease(claimed.execution_id, "worker-a", now + timedelta(seconds=2))
    assert await repository.expired_leases(now) == ()
    (expired,) = await repository.expired_leases(now + timedelta(seconds=5))
    assert (expired.execution_id, expired.lease_owner) == (claimed.execution_id, "worker-a")


@pytest.mark.asyncio
async def test_executions_require_an_agent_and_are_removed_with_it(session_factory) -> None:
    repository = SqlAlchemyExecutionRepository(session_factory)
    with pytest.raises(PersistenceError):
        await repository.add(Execution(agent_id=uuid4()))

    owner = await agent_id(session_factory)
    execution = await queued(repository, owner)
    await SqlAlchemyAgentRepository(session_factory).delete(owner)

    assert await repository.get(execution.execution_id) is None
    assert await repository.history(execution.execution_id) == ()


@pytest.mark.asyncio
async def test_list_is_newest_first_and_filters_by_agent(session_factory) -> None:
    repository = SqlAlchemyExecutionRepository(session_factory)
    first_agent, second_agent = await agent_id(session_factory), await agent_id(session_factory)
    a = await queued(repository, first_agent)
    b = await queued(repository, second_agent)
    c = await queued(repository, first_agent)

    assert [e.execution_id for e in await repository.list()] == [c.execution_id, b.execution_id, a.execution_id]
    assert [e.execution_id for e in await repository.list(first_agent)] == [c.execution_id, a.execution_id]
