"""Process-local WorkflowRepository, the default when no database is wired in."""

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from backend.app.core.core_services.persistence import PersistenceConflictError, PersistenceError
from backend.app.core.workflow_runtime.application.repositories import WorkflowRepository
from backend.app.core.workflow_runtime.domain.models import Workflow, WorkflowDefinition, WorkflowStatus


_LEASED = {WorkflowStatus.RUNNING, WorkflowStatus.PAUSED}


class InMemoryWorkflowRepository(WorkflowRepository):
    def __init__(self, history_size: int = 1000) -> None:
        self._limit = history_size
        self._definitions: dict[tuple[UUID, int], WorkflowDefinition] = {}
        self._runs: dict[UUID, Workflow] = {}
        self._order: list[UUID] = []

    async def add_definition(self, definition: WorkflowDefinition) -> WorkflowDefinition:
        key = (definition.definition_id, definition.version)
        if key in self._definitions:
            raise PersistenceConflictError("That workflow definition version already exists.")
        self._definitions[key] = definition
        return definition

    async def get_definition(self, definition_id: UUID, version: int | None = None) -> WorkflowDefinition | None:
        versions = [d for (i, _), d in self._definitions.items() if i == definition_id]
        if version is not None:
            return next((d for d in versions if d.version == version), None)
        return max(versions, key=lambda d: d.version, default=None)

    async def list_definitions(self) -> tuple[WorkflowDefinition, ...]:
        latest: dict[UUID, WorkflowDefinition] = {}
        for definition in self._definitions.values():
            if definition.definition_id not in latest or definition.version > latest[definition.definition_id].version:
                latest[definition.definition_id] = definition
        return tuple(sorted(latest.values(), key=lambda d: d.created_at, reverse=True))

    async def add_run(self, run: Workflow) -> Workflow:
        stored = replace(run, version=1)
        self._runs[stored.workflow_id] = stored
        self._order.append(stored.workflow_id)
        while len(self._order) > self._limit:
            self._runs.pop(self._order.pop(0), None)
        return stored

    async def save_run(self, current: Workflow, updated: Workflow) -> Workflow:
        stored = self._runs.get(current.workflow_id)
        if stored is None:
            raise PersistenceError("The workflow run no longer exists in storage.")
        if stored.version != current.version:
            raise PersistenceConflictError("The workflow run changed concurrently.")
        saved = replace(updated, version=current.version + 1)
        self._runs[saved.workflow_id] = saved
        return saved

    async def get_run(self, run_id: UUID) -> Workflow | None:
        return self._runs.get(run_id)

    async def list_runs(self, limit: int = 200) -> tuple[Workflow, ...]:
        return tuple(self._runs[i] for i in reversed(self._order) if i in self._runs)[:limit]

    async def delete_run(self, run_id: UUID) -> None:
        self._runs.pop(run_id, None)
        if run_id in self._order:
            self._order.remove(run_id)

    async def claim_next_run(self, owner: str, lease_expires_at: datetime) -> Workflow | None:
        for run_id in self._order:
            run = self._runs.get(run_id)
            if run is not None and run.status is WorkflowStatus.QUEUED:
                claimed = replace(
                    run.with_updates(status=WorkflowStatus.RUNNING, lease_owner=owner, lease_expires_at=lease_expires_at),
                    version=run.version + 1,
                )
                self._runs[run_id] = claimed
                return claimed
        return None

    async def renew_run_lease(self, run_id: UUID, owner: str, lease_expires_at: datetime) -> bool:
        run = self._runs.get(run_id)
        if run is None or run.lease_owner != owner or run.status not in _LEASED:
            return False
        self._runs[run_id] = replace(run, lease_expires_at=lease_expires_at)
        return True

    async def expired_runs(self, now: datetime) -> tuple[Workflow, ...]:
        return tuple(
            run
            for run in self._runs.values()
            if run.status in _LEASED and (run.lease_expires_at is None or run.lease_expires_at < now)
        )
