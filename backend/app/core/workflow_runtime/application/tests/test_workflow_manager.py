import asyncio

import pytest

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.task import TaskStatus
from backend.app.core.tool_runtime.domain.tool import builtin_tools
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.domain.exceptions import WorkflowValidationError
from backend.app.core.workflow_runtime.domain.models import WorkflowStatus, WorkflowTask, WorkflowTaskStatus


class Tools:
    async def execute(self, *, tool_name, arguments, metadata):
        await asyncio.sleep(arguments.get("delay", 0))
        class Result: status = TaskStatus.COMPLETED; result = type("Output", (), {"output": {"tool": tool_name}, "error": None})()
        return Result()


def task(task_id: str, dependencies: tuple[str, ...] = (), **arguments: object) -> WorkflowTask:
    return WorkflowTask(task_id=task_id, name=task_id, configuration={"tool_name": "echo", "tool_arguments": arguments}, dependencies=dependencies)


@pytest.mark.asyncio
async def test_sequential_tasks_unlock_and_complete() -> None:
    manager = WorkflowManager(Tools(), EventBus())
    workflow = await manager.create(name="sequence", tasks=(task("a"), task("b", ("a",))))
    await manager.start(workflow.workflow_id); complete = await manager.wait(workflow.workflow_id)
    assert complete.status is WorkflowStatus.COMPLETED
    assert [item.status for item in complete.tasks] == [WorkflowTaskStatus.COMPLETED, WorkflowTaskStatus.COMPLETED]
    assert complete.tasks[1].started_at >= complete.tasks[0].finished_at
    await manager.shutdown()


@pytest.mark.asyncio
async def test_parallel_dependencies_unlock_once() -> None:
    manager = WorkflowManager(Tools(), EventBus())
    workflow = await manager.create(name="parallel", tasks=(task("a"), task("b", ("a",), delay=.01), task("c", ("a",), delay=.01), task("d", ("b", "c"))))
    await manager.start(workflow.workflow_id); complete = await manager.wait(workflow.workflow_id)
    assert complete.status is WorkflowStatus.COMPLETED
    assert complete.tasks[-1].started_at >= complete.tasks[1].finished_at
    assert complete.tasks[-1].started_at >= complete.tasks[2].finished_at
    await manager.shutdown()


@pytest.mark.asyncio
async def test_invalid_graph_is_rejected_before_storage() -> None:
    manager = WorkflowManager(Tools(), EventBus())
    with pytest.raises(WorkflowValidationError, match="cycle"):
        await manager.create(name="cycle", tasks=(task("a", ("b",)), task("b", ("a",))))
    with pytest.raises(WorkflowValidationError, match="missing"):
        await manager.create(name="missing", tasks=(task("a", ("nope",)),))


@pytest.mark.asyncio
async def test_cancel_marks_the_running_tool_task_terminal() -> None:
    bus = EventBus()
    registry = ToolRegistry(bus)
    tools = ToolRuntimeManager(registry, ToolExecutor(registry, bus), bus)
    for tool in builtin_tools():
        await tools.register(tool)
    manager = WorkflowManager(tools, bus)
    step = WorkflowTask(task_id="wait", name="wait", configuration={"tool_name": "delay", "tool_arguments": {"seconds": 3}})
    workflow = await manager.create(name="cancel-delay", tasks=(step,))
    await manager.start(workflow.workflow_id)
    for _ in range(200):
        if tools.history() and tools.history()[0].status is TaskStatus.RUNNING:
            break
        await asyncio.sleep(0.01)
    assert tools.history()[0].status is TaskStatus.RUNNING

    cancelled = await manager.cancel(workflow.workflow_id)
    for _ in range(200):
        if tools.history()[0].status is not TaskStatus.RUNNING:
            break
        await asyncio.sleep(0.01)

    assert cancelled.tasks[0].status is WorkflowTaskStatus.CANCELLED
    (tool_task,) = tools.history()
    assert tool_task.status is TaskStatus.FAILED
    assert tool_task.finished_at is not None
    assert tool_task.result is not None and tool_task.result.metadata["cancelled"] is True
    await manager.shutdown()
