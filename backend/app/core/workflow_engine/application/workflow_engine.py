"""Application service for sequential asynchronous workflow execution."""

from threading import RLock

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.workflow_engine.domain.exceptions import (
    DuplicateWorkflowError,
    InvalidWorkflowNameError,
    WorkflowNotFoundError,
)
from backend.app.core.workflow_engine.domain.workflow import Workflow
from backend.app.core.workflow_engine.domain.workflow_context import WorkflowContext


class WorkflowEngine:
    """Register and execute named workflows through an injected Event Bus."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._workflows: dict[str, Workflow] = {}
        self._lock = RLock()

    async def register(self, workflow: Workflow) -> None:
        """Register a workflow under its unique name."""
        if not isinstance(workflow, Workflow):
            raise TypeError("Registered workflows must implement the Workflow base class.")
        self._validate_workflow_name(workflow.name)

        with self._lock:
            if workflow.name in self._workflows:
                raise DuplicateWorkflowError(workflow.name)
            self._workflows[workflow.name] = workflow

    async def unregister(self, workflow_name: str) -> Workflow:
        """Remove and return a registered workflow."""
        self._validate_workflow_name(workflow_name)
        with self._lock:
            try:
                return self._workflows.pop(workflow_name)
            except KeyError as error:
                raise WorkflowNotFoundError(workflow_name) from error

    async def resolve(self, workflow_name: str) -> Workflow:
        """Resolve a workflow by name."""
        self._validate_workflow_name(workflow_name)
        with self._lock:
            try:
                return self._workflows[workflow_name]
            except KeyError as error:
                raise WorkflowNotFoundError(workflow_name) from error

    async def execute(
        self,
        workflow_name: str,
        context: WorkflowContext | None = None,
    ) -> WorkflowContext:
        """Execute workflow steps in order and return their shared context."""
        workflow = await self.resolve(workflow_name)
        workflow_context = context if context is not None else WorkflowContext()
        event_payload = {
            "workflow_name": workflow.name,
            "context": workflow_context,
        }
        await self._event_bus.publish("workflow.started", event_payload)

        for step in workflow.steps:
            await step.execute(workflow_context)

        await self._event_bus.publish("workflow.completed", event_payload)
        return workflow_context

    async def registered_names(self) -> tuple[str, ...]:
        """Return a snapshot of registered workflow names."""
        with self._lock:
            return tuple(self._workflows)

    @staticmethod
    def _validate_workflow_name(workflow_name: object) -> None:
        if not isinstance(workflow_name, str) or not workflow_name.strip():
            raise InvalidWorkflowNameError("Workflow names must be non-empty strings.")
