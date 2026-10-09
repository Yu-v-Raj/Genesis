"""Durable workflow coordination: versioned definitions, runs, a run worker, and recovery.

Each step's state change is persisted before its effect: a step is stored as RUNNING
*before* its tool is called and as COMPLETED/FAILED after, so after a crash Genesis knows
exactly which steps finished and which were in flight. Tools run through
ToolRuntimeManager, as before.

Recovery (startup and every dispatcher tick) only touches runs whose lease expired:
in-flight steps of side-effect-free tools return to PENDING and re-run; in-flight steps
of tools that may have side effects become INTERRUPTED and the run waits for a person to
retry (with acknowledgement) or cancel it. Completed steps are never re-run.
"""

import asyncio
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.task import TaskStatus
from backend.app.core.workflow_runtime.application.in_memory_repository import InMemoryWorkflowRepository
from backend.app.core.workflow_runtime.application.repositories import WorkflowRepository
from backend.app.core.workflow_runtime.domain.events import WorkflowEvent
from backend.app.core.workflow_runtime.domain.exceptions import (
    WorkflowLifecycleError,
    WorkflowNotFoundError,
    WorkflowRetryError,
    WorkflowValidationError,
)
from backend.app.core.workflow_runtime.domain.lifecycle import (
    FINAL_RUN_STATUSES,
    FINISHED_RUN_STATUSES,
    RESETTABLE_STEP_STATUSES,
    RunRetryDecision,
    can_transition_run,
    run_retry_decision,
)
from backend.app.core.workflow_runtime.domain.models import (
    Workflow,
    WorkflowDefinition,
    WorkflowStatus,
    WorkflowTask,
    WorkflowTaskStatus,
    utc_now,
)


INTERRUPTED_RUN_MESSAGE = (
    "Genesis stopped while a step that may have external effects was running. "
    "Its outcome is unknown, so the run was not resumed automatically."
)
INTERRUPTED_STEP_MESSAGE = "Interrupted while running; the outcome is unknown."


class WorkflowManager:
    """Own workflow definitions and runs, and coordinate run steps through Tool Runtime."""

    def __init__(
        self,
        tools: ToolRuntimeManager,
        event_bus: EventBus,
        history_size: int = 1000,
        *,
        repository: WorkflowRepository | None = None,
        worker_id: str = "local",
        lease_seconds: float = 30.0,
        concurrency: int = 4,
    ) -> None:
        self._tools, self._events = tools, event_bus
        self._repository = repository or InMemoryWorkflowRepository(history_size)
        self._worker_id = worker_id
        self._lease = timedelta(seconds=lease_seconds)
        self._tick_seconds = lease_seconds / 3
        self._concurrency = concurrency
        self._lock = asyncio.Lock()
        # Transient per-process handles, never persisted.
        self._workers: dict[UUID, asyncio.Task[None]] = {}
        self._wake: dict[UUID, asyncio.Event] = {}
        self._dispatcher: asyncio.Task[None] | None = None
        self._dispatcher_wake = asyncio.Event()
        self._closing = False

    # ---------------------------------------------------------------- definitions

    async def create_definition(
        self, *, name: str, description: str = "", tasks: tuple[WorkflowTask, ...], metadata: Mapping[str, object] | None = None
    ) -> WorkflowDefinition:
        self._validate(tasks)
        definition = WorkflowDefinition(name=name, description=description, tasks=tasks, metadata={} if metadata is None else metadata)
        definition = await self._repository.add_definition(definition)
        await self._publish_definition("workflow.definition.created", definition)
        return definition

    async def update_definition(
        self, definition_id: UUID, *, name: str, description: str = "", tasks: tuple[WorkflowTask, ...], metadata: Mapping[str, object] | None = None
    ) -> WorkflowDefinition:
        """Store a new version. Existing runs keep the version they were created from."""
        current = await self.get_definition(definition_id)
        self._validate(tasks)
        definition = await self._repository.add_definition(
            WorkflowDefinition(
                definition_id=definition_id,
                version=current.version + 1,
                name=name,
                description=description,
                tasks=tasks,
                metadata={} if metadata is None else metadata,
            )
        )
        await self._publish_definition("workflow.definition.updated", definition)
        return definition

    async def get_definition(self, definition_id: UUID, version: int | None = None) -> WorkflowDefinition:
        definition = await self._repository.get_definition(definition_id, version)
        if definition is None:
            raise WorkflowNotFoundError(f"Workflow definition {definition_id} was not found.")
        return definition

    async def list_definitions(self) -> tuple[WorkflowDefinition, ...]:
        return await self._repository.list_definitions()

    async def create_run(self, definition_id: UUID, *, version: int | None = None, start: bool = False) -> Workflow:
        """Create a run from a definition version (the latest by default)."""
        definition = await self.get_definition(definition_id, version)
        run = await self._repository.add_run(definition.new_run())
        await self._publish("workflow.created", run)
        return await self.start(run.workflow_id) if start else run

    # ----------------------------------------------------------------------- runs

    async def create(self, *, name: str, description: str = "", tasks: tuple[WorkflowTask, ...], metadata: Mapping[str, object] | None = None) -> Workflow:
        """Define a workflow and create its first run in one call (the original contract)."""
        definition = await self.create_definition(name=name, description=description, tasks=tasks, metadata=metadata)
        return await self.create_run(definition.definition_id)

    async def start(self, workflow_id: UUID) -> Workflow:
        def queue(wf: Workflow) -> Workflow:
            _require(wf, {WorkflowStatus.CREATED}, "Only created workflows can be started.")
            return wf.with_updates(status=WorkflowStatus.QUEUED)

        run = await self._update(workflow_id, queue, "workflow.queued")
        self._ensure_dispatcher()
        return run

    async def pause(self, workflow_id: UUID) -> Workflow:
        def pause(wf: Workflow) -> Workflow:
            _require(wf, {WorkflowStatus.RUNNING}, "Only running workflows can be paused.")
            return wf.with_updates(status=WorkflowStatus.PAUSED)

        run = await self._update(workflow_id, pause, "workflow.paused")
        if workflow_id in self._wake:
            self._wake[workflow_id].clear()
        return run

    async def resume(self, workflow_id: UUID) -> Workflow:
        """Resume a paused run; if no worker in this process holds it, queue it for one."""
        local = workflow_id in self._workers and not self._workers[workflow_id].done()

        def resume(wf: Workflow) -> Workflow:
            _require(wf, {WorkflowStatus.PAUSED}, "Only paused workflows can be resumed.")
            if local:
                return wf.with_updates(status=WorkflowStatus.RUNNING)
            return wf.with_updates(status=WorkflowStatus.QUEUED, lease_owner=None, lease_expires_at=None)

        run = await self._update(workflow_id, resume, "workflow.resumed")
        if local:
            self._wake[workflow_id].set()
        else:
            self._ensure_dispatcher()
        return run

    async def cancel(self, workflow_id: UUID) -> Workflow:
        def cancel(wf: Workflow) -> Workflow:
            if wf.status in FINAL_RUN_STATUSES or wf.status is WorkflowStatus.FAILED:
                raise WorkflowLifecycleError("Terminal workflows cannot be cancelled.")
            tasks = tuple(
                task if task.status in {WorkflowTaskStatus.COMPLETED, WorkflowTaskStatus.FAILED} else task.with_updates(status=WorkflowTaskStatus.CANCELLED, finished_at=utc_now())
                for task in wf.tasks
            )
            return wf.with_updates(status=WorkflowStatus.CANCELLED, tasks=tasks, lease_owner=None, lease_expires_at=None)

        run = await self._update(workflow_id, cancel, "workflow.cancelled")
        if workflow_id in self._wake:
            self._wake[workflow_id].set()
        worker = self._workers.get(workflow_id)
        if worker is not None:
            worker.cancel()
        return run

    async def retry(self, workflow_id: UUID, *, acknowledge_side_effects: bool = False) -> Workflow:
        """Re-run unfinished steps of a failed or interrupted run; completed steps are kept."""
        current = await self.get(workflow_id)
        decision = self.retry_decision(current)
        if not decision.allowed:
            raise WorkflowRetryError(decision.reason)
        if decision.requires_acknowledgement and not acknowledge_side_effects:
            raise WorkflowRetryError(decision.reason, requires_acknowledgement=True)

        def reset(wf: Workflow) -> Workflow:
            if wf.status is not current.status:
                raise WorkflowLifecycleError("The run changed; reload it and try again.")
            tasks = tuple(
                task.with_updates(status=WorkflowTaskStatus.PENDING, started_at=None, finished_at=None, result=None, error=None)
                if task.status in RESETTABLE_STEP_STATUSES
                else task
                for task in wf.tasks
            )
            return wf.with_updates(status=WorkflowStatus.QUEUED, tasks=tasks, attempt=wf.attempt + 1, error=None, lease_owner=None, lease_expires_at=None)

        run = await self._update(workflow_id, reset, "workflow.retried")
        self._ensure_dispatcher()
        return run

    def retry_decision(self, run: Workflow) -> RunRetryDecision:
        uncertain = tuple(
            task.task_id
            for task in run.tasks
            if task.status is WorkflowTaskStatus.INTERRUPTED and self._may_have_side_effects(task)
        )
        return run_retry_decision(run.status, uncertain_side_effect_steps=uncertain)

    async def delete(self, workflow_id: UUID) -> Workflow:
        run = await self.get(workflow_id)
        if run.status not in FINISHED_RUN_STATUSES and run.status is not WorkflowStatus.CREATED:
            raise WorkflowLifecycleError("Cancel a running workflow before deleting it.")
        await self._repository.delete_run(workflow_id)
        self._wake.pop(workflow_id, None)
        return run

    async def wait(self, workflow_id: UUID) -> Workflow:
        """Wait until the run finishes or pauses (used by tests and scripts)."""
        while True:
            worker = self._workers.get(workflow_id)
            if worker is not None:
                try:
                    await worker
                except asyncio.CancelledError:
                    pass
            run = await self.get(workflow_id)
            if run.status not in {WorkflowStatus.QUEUED, WorkflowStatus.RUNNING}:
                return run
            self._ensure_dispatcher()
            await asyncio.sleep(0.005)

    async def get(self, workflow_id: UUID) -> Workflow:
        run = await self._repository.get_run(workflow_id)
        if run is None:
            raise WorkflowNotFoundError(f"Workflow {workflow_id} was not found.")
        return run

    async def list(self) -> tuple[Workflow, ...]:
        return await self._repository.list_runs()

    async def history(self, workflow_id: UUID) -> tuple[WorkflowTask, ...]:
        return (await self.get(workflow_id)).tasks

    # --------------------------------------------------------- worker / recovery

    async def start_worker(self) -> None:
        self._closing = False
        await self.recover()
        self._ensure_dispatcher()

    async def shutdown(self, grace_seconds: float = 5.0) -> None:
        """Stop claiming runs; give in-flight steps a moment, then interrupt the rest."""
        self._closing = True
        self._dispatcher_wake.set()
        if self._dispatcher is not None:
            self._dispatcher.cancel()
            await asyncio.gather(self._dispatcher, return_exceptions=True)
            self._dispatcher = None
        workers = list(self._workers.values())
        if workers:
            _, pending = await asyncio.wait(workers, timeout=grace_seconds)
            for task in pending:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
        # Steps cut off here are resolved by recover() on the next start, once the lease
        # has expired, exactly as after a crash.

    async def recover(self) -> tuple[Workflow, ...]:
        recovered: list[Workflow] = []
        for stale in await self._repository.expired_runs(datetime.now(UTC)):
            if stale.workflow_id in self._workers and not self._workers[stale.workflow_id].done():
                continue
            if stale.status is WorkflowStatus.PAUSED and stale.lease_owner is None and not any(t.status in {WorkflowTaskStatus.RUNNING, WorkflowTaskStatus.READY} for t in stale.tasks):
                continue  # already resolved; waiting for a person to resume it
            try:
                recovered.append(await self._recover_run(stale))
            except (PersistenceConflictError, WorkflowLifecycleError):
                continue
        if recovered:
            self._dispatcher_wake.set()
        return tuple(recovered)

    async def _recover_run(self, stale: Workflow) -> Workflow:
        interrupted_steps: list[WorkflowTask] = []

        def resolve(wf: Workflow) -> Workflow:
            if wf.version != stale.version:
                raise WorkflowLifecycleError("The run changed during recovery.")
            tasks: list[WorkflowTask] = []
            for task in wf.tasks:
                if task.status is WorkflowTaskStatus.RUNNING and self._may_have_side_effects(task):
                    task = task.with_updates(status=WorkflowTaskStatus.INTERRUPTED, error=INTERRUPTED_STEP_MESSAGE, finished_at=utc_now())
                    interrupted_steps.append(task)
                elif task.status in {WorkflowTaskStatus.RUNNING, WorkflowTaskStatus.READY}:
                    # Never started, or side-effect free: safe to run again.
                    task = task.with_updates(status=WorkflowTaskStatus.PENDING, started_at=None)
                tasks.append(task)
            if interrupted_steps:
                return wf.with_updates(status=WorkflowStatus.INTERRUPTED, tasks=tuple(tasks), error=INTERRUPTED_RUN_MESSAGE, lease_owner=None, lease_expires_at=None)
            target = WorkflowStatus.PAUSED if wf.status is WorkflowStatus.PAUSED else WorkflowStatus.QUEUED
            return wf.with_updates(status=target, tasks=tuple(tasks), lease_owner=None, lease_expires_at=None)

        run = await self._update(stale.workflow_id, resolve, None)
        for task in interrupted_steps:
            await self._publish("workflow.task.interrupted", run, task)
        await self._publish("workflow.interrupted" if interrupted_steps else "workflow.recovered", run)
        return run

    def _ensure_dispatcher(self) -> None:
        if self._closing:
            return
        if self._dispatcher is None or self._dispatcher.done():
            self._dispatcher = asyncio.create_task(self._dispatch_loop(), name="workflow-dispatcher")
        self._dispatcher_wake.set()

    async def _dispatch_loop(self) -> None:
        while not self._closing:
            self._dispatcher_wake.clear()
            try:
                until = self._lease_until()
                for run_id, worker in list(self._workers.items()):
                    if not worker.done():
                        await self._repository.renew_run_lease(run_id, self._worker_id, until)
                await self.recover()
                while sum(not w.done() for w in self._workers.values()) < self._concurrency and not self._closing:
                    claimed = await self._repository.claim_next_run(self._worker_id, self._lease_until())
                    if claimed is None:
                        break
                    await self._publish("workflow.started", claimed)
                    self._wake[claimed.workflow_id] = asyncio.Event()
                    self._wake[claimed.workflow_id].set()
                    worker = asyncio.create_task(self._run(claimed.workflow_id), name=f"workflow-{claimed.workflow_id}")
                    self._workers[claimed.workflow_id] = worker
                    worker.add_done_callback(lambda _t: self._dispatcher_wake.set())
            except PersistenceError as error:
                logger.error("Workflow dispatcher could not reach storage", extra={"genesis_context": {"error": str(error)}})
            try:
                await asyncio.wait_for(self._dispatcher_wake.wait(), timeout=self._tick_seconds)
            except TimeoutError:
                pass

    async def _run(self, workflow_id: UUID) -> None:
        try:
            while True:
                await self._wake[workflow_id].wait()
                event = ""
                async with self._lock:
                    workflow = await self.get(workflow_id)
                    if workflow.status in FINISHED_RUN_STATUSES:
                        return
                    if workflow.status is WorkflowStatus.PAUSED:
                        self._wake[workflow_id].clear()
                        continue
                    if workflow.lease_owner != self._worker_id:
                        return  # ownership was lost; another worker or recovery took over
                    ready = [task for task in workflow.tasks if task.status is WorkflowTaskStatus.PENDING and all(self._task(workflow, dep).status is WorkflowTaskStatus.COMPLETED for dep in task.dependencies)]
                    if not ready:
                        if all(task.status is WorkflowTaskStatus.COMPLETED for task in workflow.tasks):
                            workflow = await self._save(workflow, workflow.with_updates(status=WorkflowStatus.COMPLETED, lease_owner=None, lease_expires_at=None))
                            event = "workflow.completed"
                        elif any(task.status is WorkflowTaskStatus.FAILED for task in workflow.tasks):
                            workflow = await self._save(workflow, self._block_dependents(workflow).with_updates(status=WorkflowStatus.FAILED, error="One or more steps failed.", lease_owner=None, lease_expires_at=None))
                            event = "workflow.failed"
                        else:
                            return
                    else:
                        updated = workflow
                        for task in ready:
                            updated = updated.with_task(task.with_updates(status=WorkflowTaskStatus.READY))
                        workflow = await self._save(workflow, updated)
                if event:
                    await self._publish(event, workflow)
                    return
                for task in ready:
                    await self._publish("workflow.task.ready", workflow, task)
                await asyncio.gather(*(self._dispatch(workflow_id, task.task_id) for task in ready))
        except asyncio.CancelledError:
            return
        except (PersistenceConflictError, WorkflowLifecycleError, WorkflowNotFoundError):
            return  # changed elsewhere (cancelled, deleted, recovered); never overwrite it
        finally:
            self._workers.pop(workflow_id, None)

    async def _dispatch(self, workflow_id: UUID, task_id: str) -> None:
        async with self._lock:
            workflow = await self.get(workflow_id); task = self._task(workflow, task_id)
            if workflow.status is not WorkflowStatus.RUNNING or task.status is not WorkflowTaskStatus.READY: return
            task = task.with_updates(status=WorkflowTaskStatus.RUNNING, started_at=utc_now())
            # Checkpoint: stored as RUNNING before the tool can have any effect.
            workflow = await self._save(workflow, workflow.with_task(task))
        await self._publish("workflow.task.started", workflow, task)
        try:
            result = await self._tools.execute(tool_name=str(task.configuration["tool_name"]), arguments=task.configuration.get("tool_arguments", {}), metadata={"workflow_id": str(workflow_id), "workflow_task_id": task_id, "workflow_attempt": workflow.attempt})
            successful = result.status is TaskStatus.COMPLETED
            updated = task.with_updates(status=WorkflowTaskStatus.COMPLETED if successful else WorkflowTaskStatus.FAILED, result=result.result.output if result.result else None, error=None if successful else (result.result.error if result.result else "Tool task failed"), finished_at=utc_now())
        except asyncio.CancelledError:
            raise  # the step stays RUNNING in storage; recovery decides what it means
        except Exception as error:
            updated = task.with_updates(status=WorkflowTaskStatus.FAILED, error=str(error), finished_at=utc_now())
        async with self._lock:
            workflow = await self.get(workflow_id)
            if workflow.status not in {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED}:
                return  # cancelled or recovered meanwhile
            workflow = await self._save(workflow, workflow.with_task(updated))
        await self._publish("workflow.task.completed" if updated.status is WorkflowTaskStatus.COMPLETED else "workflow.task.failed", workflow, updated)

    # -------------------------------------------------------------------- helpers

    async def _update(self, workflow_id: UUID, change: Callable[[Workflow], Workflow], event: str | None) -> Workflow:
        async with self._lock:
            current = await self.get(workflow_id)
            updated = change(current)
            if not can_transition_run(current.status, updated.status) and updated.status is not current.status:
                raise WorkflowLifecycleError(f"A {current.status.value} workflow cannot become {updated.status.value}.")
            saved = await self._save(current, updated)
        if event:
            await self._publish(event, saved)
        return saved

    async def _save(self, current: Workflow, updated: Workflow) -> Workflow:
        return await self._repository.save_run(current, updated)

    def _may_have_side_effects(self, task: WorkflowTask) -> bool:
        try:
            return self._tools.get_tool(str(task.configuration["tool_name"])).definition.side_effects
        except Exception:
            return True  # unknown tools are assumed to have effects

    def _validate(self, tasks: tuple[WorkflowTask, ...]) -> None:
        ids = [task.task_id for task in tasks]
        if len(ids) != len(set(ids)): raise WorkflowValidationError("Workflow task IDs must be unique.")
        known = set(ids)
        for task in tasks:
            if task.task_id in task.dependencies: raise WorkflowValidationError(f"Task {task.task_id!r} cannot depend on itself.")
            if not set(task.dependencies) <= known: raise WorkflowValidationError(f"Task {task.task_id!r} references a missing dependency.")
            tool_name = task.configuration.get("tool_name")
            if not isinstance(tool_name, str): raise WorkflowValidationError("Tool tasks require tool_name.")
            if hasattr(self._tools, "get_tool"):
                try:
                    self._tools.get_tool(tool_name)
                except Exception as error:
                    raise WorkflowValidationError(f"Task {task.task_id!r} uses unknown tool {tool_name!r}.") from error
        visiting, visited = set(), set()
        def visit(task_id: str) -> None:
            if task_id in visiting: raise WorkflowValidationError("Workflow dependencies contain a cycle.")
            if task_id not in visited:
                visiting.add(task_id); [visit(dep) for dep in self._task_from(tasks, task_id).dependencies]; visiting.remove(task_id); visited.add(task_id)
        for task_id in ids: visit(task_id)

    def _lease_until(self) -> datetime:
        return datetime.now(UTC) + self._lease

    @staticmethod
    def _task_from(tasks: tuple[WorkflowTask, ...], task_id: str) -> WorkflowTask: return next(task for task in tasks if task.task_id == task_id)
    def _task(self, workflow: Workflow, task_id: str) -> WorkflowTask: return self._task_from(workflow.tasks, task_id)
    def _block_dependents(self, workflow: Workflow) -> Workflow:
        return workflow.with_updates(tasks=tuple(task if task.status in {WorkflowTaskStatus.COMPLETED, WorkflowTaskStatus.FAILED, WorkflowTaskStatus.RUNNING} else task.with_updates(status=WorkflowTaskStatus.BLOCKED, finished_at=utc_now()) for task in workflow.tasks))

    async def _publish(self, event: str, workflow: Workflow, task: WorkflowTask | None = None) -> None:
        payload: dict[str, object] = {"workflow_id": str(workflow.workflow_id), "status": workflow.status.value, "attempt": workflow.attempt}
        if workflow.definition_id is not None:
            payload.update({"definition_id": str(workflow.definition_id), "definition_version": workflow.definition_version})
        if task is not None: payload.update({"task_id": task.task_id, "task_status": task.status.value})
        await self._events.publish(WorkflowEvent(event_type=event, source="workflow_manager", payload=payload))

    async def _publish_definition(self, event: str, definition: WorkflowDefinition) -> None:
        await self._events.publish(WorkflowEvent(event_type=event, source="workflow_manager", payload={"definition_id": str(definition.definition_id), "version": definition.version}))


def _require(workflow: Workflow, allowed: set[WorkflowStatus], message: str) -> None:
    if workflow.status not in allowed:
        raise WorkflowLifecycleError(message)
