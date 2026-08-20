"""Typed REST schemas for Tool Runtime."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.core.tool_runtime.domain.task import Task
from backend.app.core.tool_runtime.domain.tool import Tool


class ToolResponse(BaseModel):
    name: str
    description: str
    version: str
    capabilities: list[str]
    permissions: list[str]
    enabled: bool
    metadata: dict[str, object]

    @classmethod
    def from_tool(cls, tool: Tool) -> "ToolResponse":
        definition = tool.definition
        return cls(name=definition.name, description=definition.description, version=definition.version, capabilities=[item.value for item in definition.capabilities], permissions=[item.value for item in definition.permissions], enabled=definition.enabled, metadata=dict(definition.metadata))


class ToolListResponse(BaseModel):
    tools: list[ToolResponse]


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    execution_id: UUID | None = None


class ToolResultResponse(BaseModel):
    status: str
    output: object | None
    logs: list[str]
    metadata: dict[str, object]
    duration: float
    error: str | None


class TaskResponse(BaseModel):
    task_id: UUID
    execution_id: UUID | None
    tool_name: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    metadata: dict[str, object]
    result: ToolResultResponse | None

    @classmethod
    def from_task(cls, task: Task) -> "TaskResponse":
        return cls(task_id=task.task_id, execution_id=task.execution_id, tool_name=task.tool_name, status=task.status.value, started_at=task.started_at, finished_at=task.finished_at, metadata=dict(task.metadata), result=None if task.result is None else ToolResultResponse(status=task.result.status.value, output=task.result.output, logs=list(task.result.logs), metadata=dict(task.result.metadata), duration=task.result.duration, error=task.result.error))


class ToolHistoryResponse(BaseModel):
    tasks: list[TaskResponse]


class ToolCapabilitiesResponse(BaseModel):
    capabilities: list[str]
