"""Coverage for deterministic Tool Runtime registration and invocation."""

import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.exceptions import DuplicateToolError
from backend.app.core.tool_runtime.domain.tool import builtin_tools


async def _manager() -> tuple[ToolRuntimeManager, list[str]]:
    bus = EventBus()
    events: list[str] = []
    bus.subscribe(lambda event: events.append(event.event_type))
    registry = ToolRegistry(bus)
    manager = ToolRuntimeManager(registry, ToolExecutor(registry, bus), bus, history_size=2)
    for tool in builtin_tools():
        await manager.register(tool)
    return manager, events


@pytest.mark.asyncio
async def test_builtins_execute_with_safe_deterministic_contracts() -> None:
    """Built-ins return their expected outputs without external capabilities."""
    manager, events = await _manager()

    echo = await manager.execute(tool_name="echo", arguments={"message": "Hello"})
    calculation = await manager.execute(tool_name="calculator", arguments={"expression": "2 + 5 * 10"})
    identifier = await manager.execute(tool_name="uuid")
    random_number = await manager.execute(tool_name="random_number", arguments={"min": 4, "max": 4})

    assert echo.result is not None and echo.result.output == "Hello"
    assert calculation.result is not None and calculation.result.output == 52
    assert identifier.result is not None and isinstance(identifier.result.output, str)
    assert random_number.result is not None and random_number.result.output == 4
    assert {"tool.executed", "tool.completed", "task.created", "task.completed"} <= set(events)


@pytest.mark.asyncio
async def test_validation_failure_is_recorded_and_history_is_bounded() -> None:
    """Invalid requests become failed tasks while history remains newest-first and bounded."""
    manager, _ = await _manager()
    invalid = await manager.execute(tool_name="calculator", arguments={"expression": "__import__('os')"})
    second = await manager.execute(tool_name="echo", arguments={"message": "two"})
    third = await manager.execute(tool_name="echo", arguments={"message": "three"})

    assert invalid.result is not None and invalid.result.error is not None
    assert [task.task_id for task in manager.history()] == [third.task_id, second.task_id]


@pytest.mark.asyncio
async def test_registry_prevents_duplicate_builtin_registration() -> None:
    """Tool names are unique registry identifiers."""
    manager, _ = await _manager()
    with pytest.raises(DuplicateToolError):
        await manager.register(builtin_tools()[0])
