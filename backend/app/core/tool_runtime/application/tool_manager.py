"""High-level task orchestration for Tool Runtime."""

from collections import deque
from collections.abc import Mapping
from threading import RLock
from uuid import UUID

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import TaskCompleted, TaskCreated, TaskFailed
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.task import Task, TaskStatus, utc_now
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus


class ToolRuntimeManager:
    """Coordinate Tool registration, task history, validation, and execution."""

    def __init__(self, registry: ToolRegistry, executor: ToolExecutor, event_bus: EventBus, history_size: int = 1000) -> None:
        if history_size < 1:
            raise ValueError("Tool history size must be positive.")
        self._registry = registry
        self._executor = executor
        self._event_bus = event_bus
        self._history_size = history_size
        self._tasks: dict[UUID, Task] = {}
        self._task_order: deque[UUID] = deque()
        self._lock = RLock()

    async def register(self, tool: Tool) -> Tool:
        """Register a Tool through the underlying registry."""
        return await self._registry.register(tool)

    async def execute(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
        execution_id: UUID | None = None,
    ) -> Task:
        """Create a task, invoke one Tool, and retain the terminal task snapshot."""
        task = Task(
            execution_id=execution_id,
            tool_name=tool_name,
            metadata={} if metadata is None else metadata,
        )
        self._save(task)
        await self._publish(TaskCreated, task)
        running = task.with_updates(status=TaskStatus.RUNNING, started_at=utc_now())
        self._save(running)
        result = await self._executor.execute(
            ToolRequest(
                tool_name=tool_name,
                execution_id=execution_id,
                task_id=task.task_id,
                arguments={} if arguments is None else arguments,
                metadata={} if metadata is None else metadata,
            )
        )
        status = TaskStatus.COMPLETED if result.status is ToolResultStatus.COMPLETED else TaskStatus.FAILED
        completed = running.with_updates(status=status, finished_at=utc_now(), result=result)
        self._save(completed)
        await self._publish(TaskCompleted if status is TaskStatus.COMPLETED else TaskFailed, completed)
        return completed

    def list_tools(self) -> tuple[Tool, ...]:
        """Return registered Tools."""
        return self._registry.list()

    def get_tool(self, tool_name: str) -> Tool:
        """Return a Tool declaration by name."""
        return self._registry.get(tool_name)

    def history(self) -> tuple[Task, ...]:
        """Return task history newest first."""
        with self._lock:
            return tuple(self._tasks[task_id] for task_id in reversed(self._task_order))

    def capabilities(self) -> tuple[str, ...]:
        """Return distinct declared capabilities in deterministic order."""
        return tuple(sorted({capability.value for tool in self.list_tools() for capability in tool.definition.capabilities}))

    def _save(self, task: Task) -> None:
        with self._lock:
            if task.task_id not in self._tasks:
                self._task_order.append(task.task_id)
            self._tasks[task.task_id] = task
            while len(self._task_order) > self._history_size:
                self._tasks.pop(self._task_order.popleft(), None)

    async def _publish(self, event_type: type[TaskCreated], task: Task) -> None:
        payload: dict[str, object] = {
            "task_id": str(task.task_id),
            "tool_name": task.tool_name,
            "status": task.status.value,
        }
        if task.execution_id is not None:
            payload["execution_id"] = str(task.execution_id)
        await self._event_bus.publish(event_type(source="tool_manager", payload=payload))
