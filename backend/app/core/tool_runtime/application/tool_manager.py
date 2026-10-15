"""High-level task orchestration for Tool Runtime."""

import asyncio
from collections import deque
from collections.abc import Mapping
from threading import RLock
from uuid import UUID

from backend.app.core.approval_gateway.domain.approval import ApprovalGateway
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import TaskCompleted, TaskCreated, TaskFailed, ToolRejected
from backend.app.core.tool_runtime.application.authorization_policy import (
    AgentToolGrants,
    ToolAuthorizationPolicy,
    WorkflowStepGrants,
    subject,
)
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.authorization import (
    ToolAuthorizationDecision,
    ToolAuthorizationError,
    ToolExecutionContext,
)
from backend.app.core.tool_runtime.domain.task import Task, TaskStatus, utc_now
from backend.app.core.tool_runtime.domain.tool import Tool
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus


# Caller-supplied metadata is stored only under this key. Every top-level key of a task's
# metadata (caller, Agent/workflow identifiers, approval_id) is written by the server from
# the authorization context and decision, so a caller can't forge any of them.
CALLER_METADATA_KEY = "caller_metadata"


class ToolRuntimeManager:
    """Coordinate Tool registration, task history, authorization, and execution.

    ``execute`` is the only way to run a tool: every call names its caller and passes the
    authorization policy before a task is created or the tool can act.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        executor: ToolExecutor,
        event_bus: EventBus,
        history_size: int = 1000,
        *,
        approvals: ApprovalGateway | None = None,
    ) -> None:
        if history_size < 1:
            raise ValueError("Tool history size must be positive.")
        self._registry = registry
        self._executor = executor
        self._event_bus = event_bus
        self._policy = ToolAuthorizationPolicy(registry, approvals=approvals)
        self._history_size = history_size
        self._tasks: dict[UUID, Task] = {}
        self._task_order: deque[UUID] = deque()
        self._lock = RLock()

    async def register(self, tool: Tool) -> Tool:
        """Register a Tool through the underlying registry."""
        return await self._registry.register(tool)

    def bind_agent_grants(self, source: AgentToolGrants) -> None:
        """Let the Agent runtime answer which tools an Agent may use (bound once at startup)."""
        self._policy.bind_agent_grants(source)

    def bind_workflow_steps(self, source: WorkflowStepGrants) -> None:
        """Let the Workflow runtime answer what a running step may call (bound once at startup)."""
        self._policy.bind_workflow_steps(source)

    def arguments_are_valid(self, tool_name: str, arguments: Mapping[str, object]) -> bool:
        """Check arguments against the tool's schema, e.g. when a workflow step is defined."""
        return self._policy.validate_arguments(self._registry.get(tool_name), arguments)

    async def authorize(
        self, *, tool_name: str, arguments: Mapping[str, object] | None = None, context: ToolExecutionContext
    ) -> ToolAuthorizationDecision:
        """Evaluate the policy without running anything; a denial is recorded as tool.rejected."""
        decision = await self._policy.evaluate(context, tool_name, {} if arguments is None else arguments)
        if not decision.allowed:
            await self._publish_rejected(context, tool_name, decision)
        return decision

    async def execute(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object] | None = None,
        context: ToolExecutionContext,
        metadata: Mapping[str, object] | None = None,
    ) -> Task:
        """Authorize, then create a task, invoke one Tool, and retain the terminal snapshot.

        Raises ToolAuthorizationError, without creating a task or touching the tool, when
        the policy denies the call.
        """
        arguments = {} if arguments is None else arguments
        decision = await self.authorize(tool_name=tool_name, arguments=arguments, context=context)
        if not decision.allowed:
            raise ToolAuthorizationError(tool_name, decision)
        trusted: dict[str, object] = {"caller": context.caller.value, **subject(context)}
        if decision.approval_id is not None:
            trusted["approval_id"] = decision.approval_id
        if metadata:
            trusted[CALLER_METADATA_KEY] = dict(metadata)
        metadata = trusted
        execution_id = getattr(context, "execution_id", None)
        task = Task(
            execution_id=execution_id,
            tool_name=tool_name,
            metadata=metadata,
        )
        self._save(task)
        running = task
        try:
            await self._publish(TaskCreated, task)
            running = task.with_updates(status=TaskStatus.RUNNING, started_at=utc_now())
            self._save(running)
            result = await self._executor.execute(
                ToolRequest(
                    tool_name=tool_name,
                    execution_id=execution_id,
                    task_id=task.task_id,
                    arguments=arguments,
                    metadata=metadata,
                )
            )
        except asyncio.CancelledError:
            # The caller (e.g. a cancelled workflow worker) abandoned the invocation; record
            # a terminal snapshot so history never shows a task stuck in "running".
            await self._record_cancelled(running)
            raise
        status = TaskStatus.COMPLETED if result.status is ToolResultStatus.COMPLETED else TaskStatus.FAILED
        completed = running.with_updates(status=status, finished_at=utc_now(), result=result)
        self._save(completed)
        await self._publish(TaskCompleted if status is TaskStatus.COMPLETED else TaskFailed, completed)
        return completed

    async def _record_cancelled(self, task: Task) -> None:
        finished_at = utc_now()
        duration = 0.0 if task.started_at is None else max((finished_at - task.started_at).total_seconds(), 0.0)
        cancelled = task.with_updates(
            status=TaskStatus.FAILED,
            finished_at=finished_at,
            result=ToolResult(
                status=ToolResultStatus.FAILED,
                error="Tool execution was cancelled.",
                metadata={"cancelled": True},
                duration=duration,
            ),
        )
        self._save(cancelled)
        try:
            await self._publish(TaskFailed, cancelled)
        except asyncio.CancelledError:
            pass  # the snapshot is saved; a repeated cancel must not mask the original one

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
        for key in ("caller", "agent_id", "interaction_id", "workflow_id", "workflow_task_id"):
            value = task.metadata.get(key)
            if isinstance(value, str):
                payload[key] = value
        await self._event_bus.publish(event_type(source="tool_manager", payload=payload))

    async def _publish_rejected(
        self, context: ToolExecutionContext, tool_name: str, decision: ToolAuthorizationDecision
    ) -> None:
        """Record a denied request: who asked, for which tool, and a stable reason. Never arguments."""
        caller = getattr(context, "caller", None)
        payload: dict[str, object] = {
            "caller": caller.value if caller is not None else "unknown",
            "tool_name": tool_name,
            "category": decision.outcome.value,
            "reason": decision.reason.value if decision.reason is not None else None,
        }
        if caller is not None:
            payload.update(subject(context))
        await self._event_bus.publish(ToolRejected(source="tool_authorization", payload=payload))
