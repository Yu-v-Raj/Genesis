"""Pydantic contracts for workflow definitions and durable, dependency-aware runs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.api.schemas.executions import RetryInfoResponse
from backend.app.core.workflow_runtime.domain.lifecycle import RunRetryDecision
from backend.app.core.workflow_runtime.domain.models import Workflow, WorkflowDefinition, WorkflowStatus, WorkflowTask, WorkflowTaskStatus


class WorkflowTaskCreateRequest(BaseModel):
    task_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    action: str = "tool"
    tool_name: str = Field(min_length=1)
    tool_arguments: dict[str, object] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    def to_task(self) -> WorkflowTask:
        return WorkflowTask(task_id=self.task_id, name=self.name, action=self.action, configuration={"tool_name": self.tool_name, "tool_arguments": self.tool_arguments}, dependencies=tuple(self.dependencies), metadata=self.metadata)
class WorkflowCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)
    tasks: list[WorkflowTaskCreateRequest] = Field(min_length=1)
class WorkflowTaskResponse(BaseModel):
    task_id: str; workflow_id: UUID | None; name: str; action: str; configuration: dict[str, object]; dependencies: list[str]; status: WorkflowTaskStatus; created_at: datetime; started_at: datetime | None; finished_at: datetime | None; result: object | None; error: str | None; metadata: dict[str, object]
    @classmethod
    def from_task(cls, task: WorkflowTask) -> "WorkflowTaskResponse": return cls(task_id=task.task_id, workflow_id=task.workflow_id, name=task.name, action=task.action, configuration=dict(task.configuration), dependencies=list(task.dependencies), status=task.status, created_at=task.created_at, started_at=task.started_at, finished_at=task.finished_at, result=task.result, error=task.error, metadata=dict(task.metadata))
class WorkflowResponse(BaseModel):
    """One workflow run. ``definition_id``/``definition_version`` name the plan it snapshots."""
    workflow_id: UUID; name: str; description: str; status: WorkflowStatus; created_at: datetime; updated_at: datetime; metadata: dict[str, object]; tasks: list[WorkflowTaskResponse]
    definition_id: UUID | None = None
    definition_version: int | None = None
    attempt: int = 1
    error: str | None = None
    retry: RetryInfoResponse | None = None
    @classmethod
    def from_workflow(cls, workflow: Workflow, retry: RunRetryDecision | None = None) -> "WorkflowResponse":
        return cls(
            workflow_id=workflow.workflow_id, name=workflow.name, description=workflow.description, status=workflow.status,
            created_at=workflow.created_at, updated_at=workflow.updated_at, metadata=dict(workflow.metadata),
            tasks=[WorkflowTaskResponse.from_task(task) for task in workflow.tasks],
            definition_id=workflow.definition_id, definition_version=workflow.definition_version,
            attempt=workflow.attempt, error=workflow.error,
            retry=None if retry is None else RetryInfoResponse(allowed=retry.allowed, requires_acknowledgement=retry.requires_acknowledgement, reason=retry.reason),
        )
class WorkflowListResponse(BaseModel): workflows: list[WorkflowResponse]
class WorkflowTaskListResponse(BaseModel): tasks: list[WorkflowTaskResponse]


class WorkflowStepDefinitionResponse(BaseModel):
    task_id: str; name: str; action: str; configuration: dict[str, object]; dependencies: list[str]; metadata: dict[str, object]


class WorkflowDefinitionResponse(BaseModel):
    definition_id: UUID
    version: int
    name: str
    description: str
    metadata: dict[str, object]
    created_at: datetime
    tasks: list[WorkflowStepDefinitionResponse]

    @classmethod
    def from_definition(cls, definition: WorkflowDefinition) -> "WorkflowDefinitionResponse":
        return cls(
            definition_id=definition.definition_id, version=definition.version, name=definition.name,
            description=definition.description, metadata=dict(definition.metadata), created_at=definition.created_at,
            tasks=[
                WorkflowStepDefinitionResponse(task_id=t.task_id, name=t.name, action=t.action, configuration=dict(t.configuration), dependencies=list(t.dependencies), metadata=dict(t.metadata))
                for t in definition.tasks
            ],
        )


class WorkflowDefinitionListResponse(BaseModel):
    definitions: list[WorkflowDefinitionResponse]


class WorkflowRunCreateRequest(BaseModel):
    version: int | None = Field(default=None, ge=1, description="Definition version; the latest by default.")
    start: bool = Field(default=True, description="Queue the run immediately.")


class WorkflowRetryRequest(BaseModel):
    acknowledge_side_effects: bool = Field(
        default=False,
        description="Required when interrupted steps may already have had external effects.",
    )
