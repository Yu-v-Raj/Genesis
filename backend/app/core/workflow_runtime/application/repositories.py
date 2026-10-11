"""Persistence port for workflow definitions and runs.

Run updates are compare-and-set on ``Workflow.version`` and write the run and all of its
step states in one transaction, so step progress and run status never disagree.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from backend.app.core.workflow_runtime.domain.models import Workflow, WorkflowDefinition


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
    async def list_runs(self, limit: int = 200) -> tuple[Workflow, ...]:
        """Newest first."""

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
