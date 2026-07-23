"""Abstract contract for one executable Genesis workflow step."""

from abc import ABC, abstractmethod

from backend.app.core.workflow_engine.domain.workflow_context import WorkflowContext


class WorkflowStep(ABC):
    """A named asynchronous operation within a workflow."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the step's descriptive name."""

    @abstractmethod
    async def execute(self, context: WorkflowContext) -> None:
        """Execute the step against the shared workflow context."""
