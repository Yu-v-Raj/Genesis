"""Async-safe workflow coordination and bounded in-memory history."""

import asyncio
from collections import deque
from collections.abc import Mapping
from uuid import UUID

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.task import TaskStatus
from backend.app.core.workflow_runtime.domain.exceptions import WorkflowLifecycleError, WorkflowNotFoundError, WorkflowValidationError
from backend.app.core.workflow_runtime.domain.events import WorkflowEvent
from backend.app.core.workflow_runtime.domain.models import Workflow, WorkflowStatus, WorkflowTask, WorkflowTaskStatus, utc_now


TERMINAL = {WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}


class WorkflowManager:
    """Own workflow records and coordinate their dependency graph through Tool Runtime."""

    def __init__(self, tools: ToolRuntimeManager, event_bus: EventBus, history_size: int = 1000) -> None:
        self._tools, self._events, self._limit = tools, event_bus, history_size
        self._workflows: dict[UUID, Workflow] = {}
        self._order: deque[UUID] = deque()
        self._workers: dict[UUID, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._wake: dict[UUID, asyncio.Event] = {}

    async def create(self, *, name: str, description: str = "", tasks: tuple[WorkflowTask, ...], metadata: Mapping[str, object] | None = None) -> Workflow:
        self._validate(tasks)
        workflow = Workflow(name=name, description=description, tasks=tasks, metadata={} if metadata is None else metadata)
        workflow = workflow.with_updates(tasks=tuple(task.with_updates(workflow_id=workflow.workflow_id) for task in workflow.tasks))
        async with self._lock:
            self._save(workflow)
            self._wake[workflow.workflow_id] = asyncio.Event(); self._wake[workflow.workflow_id].set()
        await self._publish("workflow.created", workflow)
        return workflow

    async def start(self, workflow_id: UUID) -> Workflow:
        async with self._lock:
            workflow = self._require(workflow_id)
            if workflow.status is not WorkflowStatus.CREATED: raise WorkflowLifecycleError("Only created workflows can be started.")
            workflow = workflow.with_updates(status=WorkflowStatus.QUEUED); self._save(workflow)
            self._workers[workflow_id] = asyncio.create_task(self._run(workflow_id), name=f"workflow-{workflow_id}")
        await self._publish("workflow.queued", workflow)
        return workflow

    async def pause(self, workflow_id: UUID) -> Workflow:
        async with self._lock:
            workflow = self._require(workflow_id)
            if workflow.status is not WorkflowStatus.RUNNING: raise WorkflowLifecycleError("Only running workflows can be paused.")
            workflow = workflow.with_updates(status=WorkflowStatus.PAUSED); self._save(workflow); self._wake[workflow_id].clear()
        await self._publish("workflow.paused", workflow); return workflow

    async def resume(self, workflow_id: UUID) -> Workflow:
        async with self._lock:
            workflow = self._require(workflow_id)
            if workflow.status is not WorkflowStatus.PAUSED: raise WorkflowLifecycleError("Only paused workflows can be resumed.")
            workflow = workflow.with_updates(status=WorkflowStatus.RUNNING); self._save(workflow); self._wake[workflow_id].set()
        await self._publish("workflow.resumed", workflow); return workflow

    async def cancel(self, workflow_id: UUID) -> Workflow:
        async with self._lock:
            workflow = self._require(workflow_id)
            if workflow.status in TERMINAL: raise WorkflowLifecycleError("Terminal workflows cannot be cancelled.")
            tasks = tuple(task if task.status in {WorkflowTaskStatus.COMPLETED, WorkflowTaskStatus.FAILED} else task.with_updates(status=WorkflowTaskStatus.CANCELLED, finished_at=utc_now()) for task in workflow.tasks)
            workflow = workflow.with_updates(status=WorkflowStatus.CANCELLED, tasks=tasks); self._save(workflow); self._wake[workflow_id].set()
            worker = self._workers.get(workflow_id)
            if worker is not None: worker.cancel()
        await self._publish("workflow.cancelled", workflow); return workflow

    async def delete(self, workflow_id: UUID) -> Workflow:
        async with self._lock:
            workflow = self._require(workflow_id)
            if workflow.status not in TERMINAL and workflow.status is not WorkflowStatus.CREATED: raise WorkflowLifecycleError("Cancel a running workflow before deleting it.")
            self._workflows.pop(workflow_id); self._order.remove(workflow_id); self._wake.pop(workflow_id, None)
        return workflow

    async def wait(self, workflow_id: UUID) -> Workflow:
        worker = self._workers.get(workflow_id)
        if worker is not None:
            try: await worker
            except asyncio.CancelledError: pass
        return self.get(workflow_id)

    def get(self, workflow_id: UUID) -> Workflow: return self._require(workflow_id)
    def list(self) -> tuple[Workflow, ...]: return tuple(self._workflows[item] for item in reversed(self._order))
    def history(self, workflow_id: UUID) -> tuple[WorkflowTask, ...]: return self._require(workflow_id).tasks

    async def _run(self, workflow_id: UUID) -> None:
        async with self._lock:
            workflow = self._require(workflow_id).with_updates(status=WorkflowStatus.RUNNING); self._save(workflow)
        await self._publish("workflow.started", workflow)
        try:
            while True:
                await self._wake[workflow_id].wait()
                async with self._lock:
                    workflow = self._require(workflow_id)
                    if workflow.status in TERMINAL: return
                    ready = [task for task in workflow.tasks if task.status is WorkflowTaskStatus.PENDING and all(self._task(workflow, dep).status is WorkflowTaskStatus.COMPLETED for dep in task.dependencies)]
                    if not ready:
                        if all(task.status is WorkflowTaskStatus.COMPLETED for task in workflow.tasks):
                            workflow = workflow.with_updates(status=WorkflowStatus.COMPLETED); self._save(workflow); event = "workflow.completed"
                        elif any(task.status is WorkflowTaskStatus.FAILED for task in workflow.tasks):
                            workflow = self._block_dependents(workflow).with_updates(status=WorkflowStatus.FAILED); self._save(workflow); event = "workflow.failed"
                        else: return
                    else:
                        event = ""
                        for task in ready:
                            workflow = workflow.with_task(task.with_updates(status=WorkflowTaskStatus.READY)); self._save(workflow)
                if event:
                    await self._publish(event, workflow); return
                for task in ready: await self._publish("workflow.task.ready", self.get(workflow_id), task)
                await asyncio.gather(*(self._dispatch(workflow_id, task.task_id) for task in ready))
        except asyncio.CancelledError: return

    async def _dispatch(self, workflow_id: UUID, task_id: str) -> None:
        async with self._lock:
            workflow = self._require(workflow_id); task = self._task(workflow, task_id)
            if workflow.status is not WorkflowStatus.RUNNING or task.status is not WorkflowTaskStatus.READY: return
            task = task.with_updates(status=WorkflowTaskStatus.RUNNING, started_at=utc_now()); workflow = workflow.with_task(task); self._save(workflow)
        await self._publish("workflow.task.started", workflow, task)
        try:
            result = await self._tools.execute(tool_name=str(task.configuration["tool_name"]), arguments=task.configuration.get("tool_arguments", {}), metadata={"workflow_id": str(workflow_id), "workflow_task_id": task_id})
            successful = result.status is TaskStatus.COMPLETED
            updated = task.with_updates(status=WorkflowTaskStatus.COMPLETED if successful else WorkflowTaskStatus.FAILED, result=result.result.output if result.result else None, error=None if successful else (result.result.error if result.result else "Tool task failed"), finished_at=utc_now())
        except Exception as error:
            updated = task.with_updates(status=WorkflowTaskStatus.FAILED, error=str(error), finished_at=utc_now())
        async with self._lock:
            workflow = self._require(workflow_id)
            if workflow.status is WorkflowStatus.CANCELLED: return
            workflow = workflow.with_task(updated); self._save(workflow)
        await self._publish("workflow.task.completed" if updated.status is WorkflowTaskStatus.COMPLETED else "workflow.task.failed", workflow, updated)
        if updated.status is WorkflowTaskStatus.FAILED:
            async with self._lock:
                workflow = self._block_dependents(self._require(workflow_id)).with_updates(status=WorkflowStatus.FAILED); self._save(workflow)
            await self._publish("workflow.failed", workflow)

    def _validate(self, tasks: tuple[WorkflowTask, ...]) -> None:
        ids = [task.task_id for task in tasks]
        if len(ids) != len(set(ids)): raise WorkflowValidationError("Workflow task IDs must be unique.")
        known = set(ids)
        for task in tasks:
            if task.task_id in task.dependencies: raise WorkflowValidationError(f"Task {task.task_id!r} cannot depend on itself.")
            if not set(task.dependencies) <= known: raise WorkflowValidationError(f"Task {task.task_id!r} references a missing dependency.")
            if not isinstance(task.configuration.get("tool_name"), str): raise WorkflowValidationError("Tool tasks require tool_name.")
        visiting, visited = set(), set()
        def visit(task_id: str) -> None:
            if task_id in visiting: raise WorkflowValidationError("Workflow dependencies contain a cycle.")
            if task_id not in visited:
                visiting.add(task_id); [visit(dep) for dep in self._task_from(tasks, task_id).dependencies]; visiting.remove(task_id); visited.add(task_id)
        for task_id in ids: visit(task_id)

    @staticmethod
    def _task_from(tasks: tuple[WorkflowTask, ...], task_id: str) -> WorkflowTask: return next(task for task in tasks if task.task_id == task_id)
    def _task(self, workflow: Workflow, task_id: str) -> WorkflowTask: return self._task_from(workflow.tasks, task_id)
    def _require(self, workflow_id: UUID) -> Workflow:
        try: return self._workflows[workflow_id]
        except KeyError as error: raise WorkflowNotFoundError(f"Workflow {workflow_id} was not found.") from error
    def _save(self, workflow: Workflow) -> None:
        if workflow.workflow_id not in self._workflows: self._order.append(workflow.workflow_id)
        self._workflows[workflow.workflow_id] = workflow
        while len(self._order) > self._limit: self._workflows.pop(self._order.popleft(), None)
    def _block_dependents(self, workflow: Workflow) -> Workflow:
        return workflow.with_updates(tasks=tuple(task if task.status in {WorkflowTaskStatus.COMPLETED, WorkflowTaskStatus.FAILED} else task.with_updates(status=WorkflowTaskStatus.BLOCKED, finished_at=utc_now()) for task in workflow.tasks))
    async def _publish(self, event: str, workflow: Workflow, task: WorkflowTask | None = None) -> None:
        payload: dict[str, object] = {"workflow_id": str(workflow.workflow_id), "status": workflow.status.value}
        if task is not None: payload.update({"task_id": task.task_id, "task_status": task.status.value})
        await self._events.publish(WorkflowEvent(event_type=event, source="workflow_manager", payload=payload))
