"""High-level task orchestration for Tool Runtime."""

import asyncio
from collections import deque
from collections.abc import Mapping
from threading import RLock
from uuid import UUID

from backend.app.core.approval_gateway.domain.approval import ApprovalGateway, ApprovalOutcome, ApprovalState, redact_arguments
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.core_services.pagination import PageCursor, comes_after, newest_first
from backend.app.core.tool_runtime.application.task_repository import TaskQuery, ToolTaskRepository, matches
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.observability.domain.events import TaskCompleted, TaskCreated, TaskFailed, ToolRejected
from backend.app.core.tool_runtime.application.authorization_policy import (
    MESSAGES,
    AgentToolGrants,
    ToolAuthorizationPolicy,
    WorkflowStepGrants,
    subject,
)
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.authorization import (
    AuthorizationOutcome,
    DenialReason,
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
INTERRUPTED_TASK_MESSAGE = "Genesis stopped while this tool was running, so its outcome is unknown. It was not re-run."


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
        tasks: ToolTaskRepository | None = None,
    ) -> None:
        if history_size < 1:
            raise ValueError("Tool history size must be positive.")
        self._registry = registry
        self._executor = executor
        self._event_bus = event_bus
        self._approvals = approvals
        # Durable task history (database in the application); the in-memory cache below
        # only serves this process's ``history()``.
        self._task_store = tasks
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
        """Check arguments against the size limits and the tool's schema."""
        return self._policy.validate_arguments(self._registry.get(tool_name), arguments)

    def argument_problem(self, tool_name: str, arguments: Mapping[str, object]) -> str | None:
        """Why arguments can't be used with a tool, e.g. when a workflow step is defined."""
        return self._policy.argument_problem(self._registry.get(tool_name), arguments)

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
        approval_id = decision.approval_id
        if approval_id is not None:
            # The single use of the approval, atomically, after the policy was re-evaluated
            # just above. A concurrent caller, an expiry or a cancellation makes this fail.
            if self._approvals is None or decision.operation_digest is None or not await self._approvals.consume(
                approval_id, decision.operation_digest
            ):
                refused = ToolAuthorizationDecision(
                    outcome=AuthorizationOutcome.APPROVAL_REQUIRED,
                    reason=DenialReason.APPROVAL_UNUSABLE,
                    message=MESSAGES[DenialReason.APPROVAL_UNUSABLE],
                    approval_id=approval_id,
                )
                await self._publish_rejected(context, tool_name, refused)
                raise ToolAuthorizationError(tool_name, refused)
        trusted: dict[str, object] = {"caller": context.caller.value, **subject(context)}
        if decision.approval_id is not None:
            trusted["approval_id"] = str(decision.approval_id)
        if metadata:
            trusted[CALLER_METADATA_KEY] = dict(metadata)
        metadata = trusted
        execution_id = getattr(context, "execution_id", None)
        shown, _ = redact_arguments(arguments)
        task = Task(
            execution_id=execution_id,
            tool_name=tool_name,
            metadata=metadata,
            tool_version=self._tool_version(tool_name),
            arguments=shown,
        )
        self._save(task)
        running = task
        try:
            running = task.with_updates(status=TaskStatus.RUNNING, started_at=utc_now())
            # Durable before effect: if the task can't be recorded, the tool doesn't run.
            try:
                await self._persist(running, required=True)
            except Exception:
                self._save(running.with_updates(status=TaskStatus.FAILED, finished_at=utc_now(), result=ToolResult(status=ToolResultStatus.FAILED, error="Not run: the task could not be recorded.")))
                if approval_id is not None:
                    await self._record_approval_outcome(approval_id, task.task_id, ApprovalOutcome.FAILED, "Not run: the task could not be recorded.")
                raise
            await self._publish(TaskCreated, task)
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
            if approval_id is not None:
                await self._record_approval_outcome(approval_id, task.task_id, ApprovalOutcome.UNKNOWN, "The call was cancelled while the tool was running; its effect is unknown.")
            raise
        status = TaskStatus.COMPLETED if result.status is ToolResultStatus.COMPLETED else TaskStatus.FAILED
        completed = running.with_updates(status=status, finished_at=utc_now(), result=result)
        self._save(completed)
        await self._persist(completed)
        if approval_id is not None:
            await self._record_approval_outcome(
                approval_id,
                task.task_id,
                ApprovalOutcome.COMPLETED if status is TaskStatus.COMPLETED else ApprovalOutcome.FAILED,
                None if status is TaskStatus.COMPLETED else "The tool ran and reported a failure.",
            )
        await self._publish(TaskCompleted if status is TaskStatus.COMPLETED else TaskFailed, completed)
        return completed

    async def _record_approval_outcome(self, approval_id: UUID, task_id: UUID, outcome: ApprovalOutcome, detail: str | None) -> None:
        if self._approvals is None:
            return
        try:
            await self._approvals.record_outcome(approval_id, task_id=task_id, outcome=outcome, detail=detail)
        except (Exception, asyncio.CancelledError):
            pass  # the task snapshot is authoritative; the approval keeps "outcome unknown"

    # ------------------------------------------------------------- durable history

    async def _persist(self, task: Task, *, required: bool = False) -> None:
        if self._task_store is None:
            return
        try:
            await self._task_store.save(task)
        except Exception as error:
            if required:
                raise
            # The effect already happened; keep going, but say the history is incomplete.
            logger.error("Tool task history could not be saved", extra={"genesis_context": {"task_id": str(task.task_id), "error_type": type(error).__name__}})

    def _tool_version(self, tool_name: str) -> str | None:
        try:
            return self._registry.get(tool_name).definition.version
        except Exception:
            return None

    async def task_page(self, query: TaskQuery, *, before: PageCursor | None = None, limit: int = 50) -> tuple[Task, ...]:
        """Durable task history, newest first (this process's cache without a store)."""
        if self._task_store is not None:
            return await self._task_store.page(query, before=before, limit=limit)
        ordered = newest_first(self.history(), lambda task: task.created_at, lambda task: task.task_id)
        return tuple(t for t in ordered if comes_after(t.created_at, t.task_id, before) and matches(t, query))[:limit]

    async def get_task(self, task_id: UUID) -> Task | None:
        if self._task_store is not None:
            return await self._task_store.get(task_id)
        return next((task for task in self.history() if task.task_id == task_id), None)

    async def recover_unfinished(self) -> int:
        """Close tasks a previous process left pending or running: their effect is unknown,
        so they are recorded as failed with ``interrupted`` and never re-run."""
        if self._task_store is None:
            return 0
        closed = 0
        for task in await self._task_store.unfinished():
            finished_at = utc_now()
            interrupted = task.with_updates(
                status=TaskStatus.FAILED,
                finished_at=finished_at,
                result=ToolResult(
                    status=ToolResultStatus.FAILED,
                    error=INTERRUPTED_TASK_MESSAGE,
                    metadata={"interrupted": True},
                    duration=0.0 if task.started_at is None else max((finished_at - task.started_at).total_seconds(), 0.0),
                ),
            )
            await self._task_store.save(interrupted)
            approval = task.metadata.get("approval_id")
            if isinstance(approval, str):
                try:
                    await self._record_approval_outcome(UUID(approval), task.task_id, ApprovalOutcome.UNKNOWN, INTERRUPTED_TASK_MESSAGE)
                except ValueError:
                    pass
            await self._publish(TaskFailed, interrupted)
            closed += 1
        return closed

    # ------------------------------------------------------------ approval helpers

    async def approval_state(self, approval_id: UUID) -> ApprovalState | None:
        """Current state of a request a caller is waiting on (None if unknown or no gateway)."""
        return None if self._approvals is None else await self._approvals.state_of(approval_id)

    async def cancel_approval(self, approval_id: UUID, *, reason: str) -> None:
        """Abandon a request whose operation will no longer run (no-op if already final)."""
        if self._approvals is not None:
            await self._approvals.cancel(approval_id, reason=reason)

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
            await self._persist(cancelled)
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
        if decision.approval_id is not None:
            payload["approval_id"] = str(decision.approval_id)
        await self._event_bus.publish(ToolRejected(source="tool_authorization", payload=payload))
