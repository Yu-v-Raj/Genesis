"""Persistence port for workflow definitions and runs.

Run updates are compare-and-set on ``Workflow.version`` and write the run, all of its
step states and a timeline entry for every status change in one transaction, so step
progress, run status and history never disagree.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from backend.app.core.core_services.pagination import PageCursor
from backend.app.core.workflow_runtime.domain.models import Workflow, WorkflowDefinition, WorkflowStatus
from backend.app.core.workflow_runtime.domain.transition import WorkflowTransition


class WorkflowRepository(ABC):
    @abstractmethod
    async def add_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        """Store a new definition version; (definition_id, version) must be unique."""

    @abstractmethod
    async def get_definition(self, definition_id: UUID, version: int | None = None) -> WorkflowDefinition | None:
        """Return one version, or the latest when ``version`` is None."""

    @abstractmethod
    async def list_definitions(self) -> tuple[WorkflowDefinition, ...]:
        """Latest version of every definition, newest first."""

    @abstractmethod
    async def add_run(self, run: Workflow) -> Workflow: ...

    @abstractmethod
    async def save_run(self, current: Workflow, updated: Workflow) -> Workflow:
        """Store ``updated`` only if the stored version still equals ``current.version``."""

    @abstractmethod
    async def get_run(self, run_id: UUID) -> Workflow | None: ...

    @abstractmethod
    async def list_runs(self, limit: int = 200, *, before: PageCursor | None = None) -> tuple[Workflow, ...]:
        """Newest first by (created_at, workflow_id); ``before`` continues after that cursor."""

    @abstractmethod
    async def runs_with_status(self, statuses: tuple[WorkflowStatus, ...]) -> tuple[Workflow, ...]:
        """Every run in one of ``statuses``, however old (for recovery and resumption)."""

    @abstractmethod
    async def history(self, run_id: UUID) -> tuple[WorkflowTransition, ...]:
        """The run's recorded status changes, oldest first."""

    @abstractmethod
    async def delete_run(self, run_id: UUID) -> None: ...

    @abstractmethod
    async def claim_next_run(self, owner: str, lease_expires_at: datetime) -> Workflow | None:
        """Atomically move the oldest QUEUED run to RUNNING under ``owner``'s lease."""

    @abstractmethod
    async def renew_run_lease(self, run_id: UUID, owner: str, lease_expires_at: datetime) -> bool: ...

    @abstractmethod
    async def expired_runs(self, now: datetime) -> tuple[Workflow, ...]:
        """RUNNING or PAUSED runs whose owner stopped renewing its lease."""
