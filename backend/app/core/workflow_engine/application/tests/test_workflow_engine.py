"""Unit tests for the Genesis Workflow Engine."""

from collections.abc import Sequence

import pytest

from backend.app.core.core_services.event_bus import Event, EventBus
from backend.app.core.workflow_engine.application.workflow_engine import WorkflowEngine
from backend.app.core.workflow_engine.domain.exceptions import (
    DuplicateWorkflowError,
    WorkflowNotFoundError,
)
from backend.app.core.workflow_engine.domain.workflow import Workflow
from backend.app.core.workflow_engine.domain.workflow_context import WorkflowContext
from backend.app.core.workflow_engine.domain.workflow_step import WorkflowStep


class RecordingStep(WorkflowStep):
    """Test step that records its order and writes to context."""

    def __init__(self, name: str, events: list[str]) -> None:
        self._name = name
        self._events = events

    @property
    def name(self) -> str:
        """Return the test step name."""
        return self._name

    async def execute(self, context: WorkflowContext) -> None:
        """Record execution and share the current step through context."""
        self._events.append(self.name)
        context.data["last_step"] = self.name


class FailingStep(WorkflowStep):
    """Test step that raises during execution."""

    @property
    def name(self) -> str:
        """Return the failing test step name."""
        return "failing"

    async def execute(self, context: WorkflowContext) -> None:
        """Raise the expected test failure."""
        raise RuntimeError("workflow step failed")


class ExampleWorkflow(Workflow):
    """Concrete workflow used to test the generic engine."""

    def __init__(self, name: str, steps: Sequence[WorkflowStep]) -> None:
        self._name = name
        self._steps = steps

    @property
    def name(self) -> str:
        """Return the test workflow name."""
        return self._name

    @property
    def steps(self) -> Sequence[WorkflowStep]:
        """Return the configured test steps."""
        return self._steps


@pytest.mark.asyncio
async def test_register_and_resolve_workflow() -> None:
    """Registered workflows can be resolved by name."""
    engine = WorkflowEngine(EventBus())
    workflow = ExampleWorkflow("example", [])

    await engine.register(workflow)

    assert await engine.resolve("example") is workflow


@pytest.mark.asyncio
async def test_duplicate_registration_raises_exception() -> None:
    """Workflow names are unique within one engine."""
    engine = WorkflowEngine(EventBus())
    await engine.register(ExampleWorkflow("example", []))

    with pytest.raises(DuplicateWorkflowError, match="example"):
        await engine.register(ExampleWorkflow("example", []))


@pytest.mark.asyncio
async def test_workflow_steps_execute_sequentially_with_shared_context() -> None:
    """Workflow steps run in declared order and receive the same context."""
    events: list[str] = []
    engine = WorkflowEngine(EventBus())
    workflow = ExampleWorkflow(
        "example",
        [RecordingStep("first", events), RecordingStep("second", events)],
    )
    await engine.register(workflow)
    context = WorkflowContext(data={"request_id": "example"})

    result = await engine.execute("example", context)

    assert result is context
    assert events == ["first", "second"]
    assert context.data == {"request_id": "example", "last_step": "second"}


@pytest.mark.asyncio
async def test_step_failure_stops_workflow_and_propagates_error() -> None:
    """Failure stops later steps and remains visible to the caller."""
    events: list[str] = []
    engine = WorkflowEngine(EventBus())
    workflow = ExampleWorkflow(
        "example",
        [FailingStep(), RecordingStep("after_failure", events)],
    )
    await engine.register(workflow)

    with pytest.raises(RuntimeError, match="workflow step failed"):
        await engine.execute("example")

    assert events == []


@pytest.mark.asyncio
async def test_execution_publishes_start_and_completion_events() -> None:
    """Successful workflow execution emits lifecycle events through Event Bus."""
    event_bus = EventBus()
    event_names: list[str] = []

    async def handler(event: Event) -> None:
        event_names.append(event.name)

    event_bus.subscribe("workflow.started", handler)
    event_bus.subscribe("workflow.completed", handler)
    engine = WorkflowEngine(event_bus)
    await engine.register(ExampleWorkflow("example", []))

    await engine.execute("example")

    assert event_names == ["workflow.started", "workflow.completed"]


@pytest.mark.asyncio
async def test_unregister_removes_workflow() -> None:
    """Unregistering removes a workflow from future resolution."""
    engine = WorkflowEngine(EventBus())
    workflow = ExampleWorkflow("example", [])
    await engine.register(workflow)

    assert await engine.unregister("example") is workflow
    with pytest.raises(WorkflowNotFoundError):
        await engine.resolve("example")
