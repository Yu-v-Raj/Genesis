"""Tests for independent deterministic execution lifecycle orchestration."""

import asyncio
from uuid import uuid4

import pytest

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.execution_runtime.application.execution_executor import ExecutionExecutor
from backend.app.core.execution_runtime.application.execution_history import ExecutionHistory
from backend.app.core.execution_runtime.application.execution_manager import ExecutionManager
from backend.app.core.execution_runtime.domain.exceptions import (
    AgentNotExecutableError,
    ExecutionLifecycleError,
    ExecutionNotFoundError,
)
from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext
from backend.app.core.execution_runtime.domain.execution_status import ExecutionStatus


class FailingExecutor(ExecutionExecutor):
    """Minimal executor double that proves manager failure handling."""

    async def execute(self, context: ExecutionContext) -> str:
        raise RuntimeError("deterministic failure")


async def _manager(delay_seconds: float = 0) -> tuple[ExecutionManager, AgentManager, list[str]]:
    event_bus = EventBus()
    event_types: list[str] = []
    event_bus.subscribe(lambda event: event_types.append(event.event_type))
    registry = AgentRegistry(event_bus)
    agent_manager = AgentManager(registry, event_bus)
    manager = ExecutionManager(
        registry, ExecutionExecutor(delay_seconds), ExecutionHistory(capacity=2), event_bus
    )
    return manager, agent_manager, event_types


@pytest.mark.asyncio
async def test_execution_completes_without_changing_agent_lifecycle() -> None:
    """One initialized Agent can run work while remaining independently idle."""
    manager, agent_manager, event_types = await _manager()
    agent = await agent_manager.create_agent(name="worker", description="Runs work.", type="test")
    await agent_manager.initialize_agent(agent.id)

    execution = await manager.execute(agent.id, metadata={"request": "test"})
    await asyncio.sleep(0.01)
    completed = manager.get_execution(execution.execution_id)

    assert completed.status is ExecutionStatus.COMPLETED
    assert completed.result is not None
    assert completed.result.output == "Execution completed successfully."
    assert completed.metadata == {"request": "test"}
    assert (await agent_manager.get_context(agent.id)).current_state.value == "idle"
    assert {"execution.created", "execution.queued", "execution.started", "execution.progress", "execution.completed"} <= set(event_types)


@pytest.mark.asyncio
async def test_execution_cancellation_and_invalid_terminal_transition() -> None:
    """Cancellation terminates work and cannot be repeated."""
    manager, agent_manager, event_types = await _manager(delay_seconds=5)
    agent = await agent_manager.create_agent(name="worker", description="Runs work.", type="test")
    await agent_manager.initialize_agent(agent.id)
    execution = await manager.execute(agent.id)

    cancelled = await manager.cancel_execution(execution.execution_id)

    assert cancelled.status is ExecutionStatus.CANCELLED
    assert "execution.cancelled" in event_types
    with pytest.raises(ExecutionLifecycleError):
        await manager.cancel_execution(execution.execution_id)


@pytest.mark.asyncio
async def test_execution_failure_is_recorded_and_published() -> None:
    """Executor errors become a failed terminal execution rather than escaping a task."""
    manager, agent_manager, event_types = await _manager()
    manager._executor = FailingExecutor()
    agent = await agent_manager.create_agent(name="worker", description="Runs work.", type="test")
    await agent_manager.initialize_agent(agent.id)

    execution = await manager.execute(agent.id)
    await asyncio.sleep(0.01)

    failed = manager.get_execution(execution.execution_id)
    assert failed.status is ExecutionStatus.FAILED
    assert failed.error == "deterministic failure"
    assert "execution.failed" in event_types


@pytest.mark.asyncio
async def test_history_is_newest_first_and_bounded() -> None:
    """History replacement retains only its configured newest records."""
    manager, agent_manager, _ = await _manager()
    agent = await agent_manager.create_agent(name="worker", description="Runs work.", type="test")
    await agent_manager.initialize_agent(agent.id)
    first = await manager.create_execution(agent.id)
    second = await manager.create_execution(agent.id)
    third = await manager.create_execution(agent.id)

    assert [item.execution_id for item in manager.list_executions()] == [third.execution_id, second.execution_id]
    assert manager.list_executions(agent.id)[0].agent_id == agent.id
    with pytest.raises(ExecutionNotFoundError):
        manager.get_execution(first.execution_id)


@pytest.mark.asyncio
async def test_execution_rejects_uninitialized_and_stopped_agents() -> None:
    """Agent validation is enforced before execution creation."""
    manager, agent_manager, _ = await _manager()
    agent = await agent_manager.create_agent(name="worker", description="Runs work.", type="test")

    with pytest.raises(AgentNotExecutableError):
        await manager.create_execution(agent.id)
    await agent_manager.initialize_agent(agent.id)
    await agent_manager.stop_agent(agent.id)
    with pytest.raises(AgentNotExecutableError):
        await manager.create_execution(agent.id)


def test_executor_has_deterministic_output() -> None:
    """The executor intentionally contains no AI or external integration."""
    execution = Execution(agent_id=uuid4())
    output = asyncio.run(
        ExecutionExecutor(0).execute(
            ExecutionContext(execution_id=execution.execution_id, agent_id=execution.agent_id)
        )
    )
    assert output == "Execution completed successfully."
