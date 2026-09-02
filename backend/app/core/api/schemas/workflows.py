"""Pydantic contracts for dependency-aware workflow coordination."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from backend.app.core.workflow_runtime.domain.models import Workflow, WorkflowStatus, WorkflowTask, WorkflowTaskStatus


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
    workflow_id: UUID; name: str; description: str; status: WorkflowStatus; created_at: datetime; updated_at: datetime; metadata: dict[str, object]; tasks: list[WorkflowTaskResponse]
    @classmethod
    def from_workflow(cls, workflow: Workflow) -> "WorkflowResponse": return cls(workflow_id=workflow.workflow_id, name=workflow.name, description=workflow.description, status=workflow.status, created_at=workflow.created_at, updated_at=workflow.updated_at, metadata=dict(workflow.metadata), tasks=[WorkflowTaskResponse.from_task(task) for task in workflow.tasks])


class WorkflowListResponse(BaseModel): workflows: list[WorkflowResponse]
class WorkflowTaskListResponse(BaseModel): tasks: list[WorkflowTaskResponse]
