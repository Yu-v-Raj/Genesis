"""Read-only Operations endpoints: execution and workflow traces, durable runtime events.

Every route here only reads. Traces join each runtime's own records (executions, workflow
runs, tool tasks, approvals, runtime events) by the identifiers those records carry.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.api.dependencies.system import (
    get_agent_registry,
    get_execution_manager,
    get_operations_query,
    get_tool_runtime_manager,
    get_workflow_manager,
)
from backend.app.core.api.routers.approvals import approval_response
from backend.app.core.api.schemas.executions import ExecutionResponse, ExecutionTransitionResponse
from backend.app.core.api.schemas.operations import (
    ExecutionTraceResponse,
    ModelCallResponse,
    RuntimeEventPageResponse,
    RuntimeEventResponse,
    TraceLimits,
    WorkflowTraceResponse,
    WorkflowTransitionResponse,
)
from backend.app.core.api.schemas.tools import TaskResponse
from backend.app.core.api.schemas.workflows import WorkflowResponse
from backend.app.core.execution_runtime.application.execution_manager import ExecutionManager
from backend.app.core.execution_runtime.domain.exceptions import ExecutionNotFoundError
from backend.app.core.observability.application.operations_query import OperationsQueryService, TracePart
from backend.app.core.observability.domain.runtime_event import EventQuery
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.domain.exceptions import WorkflowNotFoundError


router = APIRouter(prefix="/api/operations", tags=["operations"])
Query_ = Annotated[OperationsQueryService, Depends(get_operations_query)]
Tools = Annotated[ToolRuntimeManager, Depends(get_tool_runtime_manager)]
Agents = Annotated[AgentRegistry, Depends(get_agent_registry)]
Workflows = Annotated[WorkflowManager, Depends(get_workflow_manager)]
Executions = Annotated[ExecutionManager, Depends(get_execution_manager)]
MODEL_CALL_EVENTS = frozenset({"llm.completed", "llm.failed"})


@router.get("/events", response_model=RuntimeEventPageResponse)
async def runtime_events(
    operations: Query_,
    before_sequence: Annotated[int | None, Query(ge=1, description="Only events older than this sequence (from next_before_sequence).")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    event_type: Annotated[str | None, Query(max_length=200, description='Exact type, or a prefix ending in "." such as "workflow."')] = None,
    execution_id: UUID | None = None,
    workflow_id: UUID | None = None,
    approval_id: UUID | None = None,
    tool_task_id: UUID | None = None,
) -> RuntimeEventPageResponse:
    """Durable runtime events, newest first, kept for RUNTIME_EVENT_RETENTION_DAYS."""
    query = EventQuery(
        execution_id=execution_id, workflow_id=workflow_id, approval_id=approval_id, tool_task_id=tool_task_id, event_type=event_type or None
    )
    page = await operations.events(query, before_sequence=before_sequence, limit=limit)
    return RuntimeEventPageResponse(
        events=[RuntimeEventResponse.from_stored(event) for event in page.events],
        next_before_sequence=page.next_before_sequence,
    )


@router.get("/executions/{execution_id}/trace", response_model=ExecutionTraceResponse)
async def execution_trace(
    execution_id: UUID, operations: Query_, executions: Executions, tools: Tools, agents: Agents, workflows: Workflows
) -> ExecutionTraceResponse:
    """One execution end to end: its timeline, model calls, tool runs, approvals and events."""
    try:
        trace = await operations.execution_trace(execution_id)
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    related = trace.related
    return ExecutionTraceResponse(
        execution=ExecutionResponse.from_execution(trace.execution, executions.retry_decision(trace.execution)),
        transitions=[ExecutionTransitionResponse.from_domain(item) for item in trace.transitions],
        model_calls=[ModelCallResponse.from_stored(event) for event in related.events if event.event_type in MODEL_CALL_EVENTS],
        tool_tasks=[TaskResponse.from_task(task) for task in related.tool_tasks],
        approvals=[await approval_response(item, tools, agents, workflows) for item in related.approvals],
        events=[RuntimeEventResponse.from_stored(event) for event in related.events],
        truncated=_limits(related),
    )


@router.get("/workflows/{workflow_id}/trace", response_model=WorkflowTraceResponse)
async def workflow_trace(
    workflow_id: UUID, operations: Query_, tools: Tools, agents: Agents, workflows: Workflows
) -> WorkflowTraceResponse:
    """One workflow run end to end: run and step timeline, tool runs, approvals and events."""
    try:
        trace = await operations.workflow_trace(workflow_id)
    except WorkflowNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    related = trace.related
    return WorkflowTraceResponse(
        run=WorkflowResponse.from_workflow(trace.run, workflows.retry_decision(trace.run)),
        transitions=[WorkflowTransitionResponse.from_domain(item) for item in trace.transitions],
        tool_tasks=[TaskResponse.from_task(task) for task in related.tool_tasks],
        approvals=[await approval_response(item, tools, agents, workflows) for item in related.approvals],
        events=[RuntimeEventResponse.from_stored(event) for event in related.events],
        truncated=_limits(related),
    )


def _limits(related: TracePart) -> TraceLimits:
    return TraceLimits(tool_tasks=related.tool_tasks_truncated, approvals=related.approvals_truncated, events=related.events_truncated)
