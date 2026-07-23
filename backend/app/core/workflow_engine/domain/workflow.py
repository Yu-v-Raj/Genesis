"""Abstract contract for sequential Genesis workflows."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from backend.app.core.workflow_engine.domain.workflow_step import WorkflowStep


class Workflow(ABC):
    """A named sequence of executable workflow steps."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the workflow's unique registry name."""

    @property
    @abstractmethod
    def steps(self) -> Sequence[WorkflowStep]:
        """Return workflow steps in their required execution order."""
