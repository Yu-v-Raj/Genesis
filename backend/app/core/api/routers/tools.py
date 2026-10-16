"""REST adapters for Tool Runtime."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from backend.app.core.api.dependencies.system import get_tool_runtime_manager
from backend.app.core.api.pagination import BeforeCursor, page_cursor
from backend.app.core.core_services.pagination import next_cursor
from backend.app.core.api.schemas.tools import ToolCapabilitiesResponse, ToolExecuteRequest, ToolHistoryResponse, ToolListResponse, ToolResponse, TaskResponse
from backend.app.core.tool_runtime.application.task_repository import TaskQuery
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.argument_limits import MAX_METADATA_BYTES, size_problem
from backend.app.core.tool_runtime.domain.authorization import (
    AuthorizationOutcome,
    DenialReason,
    OperatorTestContext,
    ToolAuthorizationError,
)
from backend.app.core.tool_runtime.domain.exceptions import ToolNotFoundError


router = APIRouter(prefix="/api/tools", tags=["tools"])
ToolManagerDependency = Annotated[ToolRuntimeManager, Depends(get_tool_runtime_manager)]


@router.get("", response_model=ToolListResponse)
def list_tools(manager: ToolManagerDependency) -> ToolListResponse:
    return ToolListResponse(tools=[ToolResponse.from_tool(tool) for tool in manager.list_tools()])


@router.get("/history", response_model=ToolHistoryResponse)
async def history(
    manager: ToolManagerDependency,
    before: BeforeCursor = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    tool_name: Annotated[str | None, Query(max_length=200)] = None,
    execution_id: UUID | None = None,
    workflow_id: UUID | None = None,
) -> ToolHistoryResponse:
    """Durable tool runs, newest first, across restarts."""
    query = TaskQuery(execution_id=execution_id, workflow_id=workflow_id, tool_name=tool_name)
    page = await manager.task_page(query, before=page_cursor(before), limit=limit + 1)
    return ToolHistoryResponse(
        tasks=[TaskResponse.from_task(task) for task in page[:limit]],
        next_before=next_cursor(page, limit, lambda task: task.created_at, lambda task: task.task_id),
    )


@router.get("/capabilities", response_model=ToolCapabilitiesResponse)
def capabilities(manager: ToolManagerDependency) -> ToolCapabilitiesResponse:
    return ToolCapabilitiesResponse(capabilities=list(manager.capabilities()))


@router.get("/{tool_name}", response_model=ToolResponse)
def get_tool(tool_name: str, manager: ToolManagerDependency) -> ToolResponse:
    try:
        return ToolResponse.from_tool(manager.get_tool(tool_name))
    except ToolNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


_DENIAL_STATUS = {
    AuthorizationOutcome.UNAVAILABLE: status.HTTP_409_CONFLICT,
    AuthorizationOutcome.NOT_ALLOWED: status.HTTP_403_FORBIDDEN,
    AuthorizationOutcome.INVALID_REQUEST: status.HTTP_422_UNPROCESSABLE_CONTENT,
    AuthorizationOutcome.APPROVAL_REQUIRED: status.HTTP_403_FORBIDDEN,
}


@router.post("/execute", response_model=TaskResponse)
async def execute_tool(request: ToolExecuteRequest, manager: ToolManagerDependency) -> TaskResponse | JSONResponse:
    """Run one tool as an operator test. Genesis does not authenticate operators, so the
    call gets no identity and only what the policy allows any test run."""
    metadata_problem = size_problem(request.metadata, max_bytes=MAX_METADATA_BYTES, what="The run's metadata")
    if metadata_problem is not None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=metadata_problem)
    if request.execution_id is not None:
        # Attaching a test run to an execution would make it look like an Agent's call.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Test runs can't be attached to an execution.",
        )
    try:
        task = await manager.execute(
            tool_name=request.tool_name,
            arguments=request.arguments,
            metadata=request.metadata,
            context=OperatorTestContext(),
        )
    except ToolAuthorizationError as error:
        decision = error.decision
        if decision.outcome is AuthorizationOutcome.APPROVAL_REQUIRED and decision.approval_id is not None:
            # Nothing ran. The exact call waits for the operator in Approvals; approving it
            # there runs it once. Repeating this request returns the same pending request.
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "detail": decision.message,
                    "outcome": decision.outcome.value,
                    "reason": decision.reason.value if decision.reason is not None else None,
                    "approval_id": str(decision.approval_id),
                },
            )
        code = (
            status.HTTP_404_NOT_FOUND
            if decision.reason is DenialReason.TOOL_NOT_FOUND
            else _DENIAL_STATUS.get(decision.outcome, status.HTTP_403_FORBIDDEN)
        )
        # `detail` stays a readable string; `outcome` and `reason` are stable codes.
        return JSONResponse(
            status_code=code,
            content={
                "detail": decision.message,
                "outcome": decision.outcome.value,
                "reason": decision.reason.value if decision.reason is not None else None,
            },
        )
    if task.result is not None and task.result.error is not None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=task.result.error)
    return TaskResponse.from_task(task)
