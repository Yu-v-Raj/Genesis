"""FastAPI adapter for independent Execution Runtime operations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.agent_runtime.domain.exceptions import AgentNotFoundError
from backend.app.core.api.dependencies.system import get_execution_manager
from backend.app.core.api.schemas.executions import (
    ExecutionCreateRequest,
    ExecutionListResponse,
    ExecutionResponse,
)
from backend.app.core.execution_runtime.application.execution_manager import ExecutionManager
from backend.app.core.execution_runtime.domain.exceptions import (
    AgentNotExecutableError,
    ExecutionLifecycleError,
    ExecutionNotFoundError,
)


router = APIRouter(tags=["executions"])
ExecutionManagerDependency = Annotated[ExecutionManager, Depends(get_execution_manager)]


@router.post("/api/agents/{agent_id}/execute", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute_agent(
    agent_id: UUID,
    request: ExecutionCreateRequest,
    manager: ExecutionManagerDependency,
) -> ExecutionResponse:
    """Create and schedule work for an initialized Agent."""
    try:
        return ExecutionResponse.from_execution(await manager.execute(agent_id, metadata=request.metadata))
    except AgentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except AgentNotExecutableError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/api/executions", response_model=ExecutionListResponse)
def list_executions(manager: ExecutionManagerDependency) -> ExecutionListResponse:
    """Return the bounded newest-first execution history."""
    return ExecutionListResponse(
        executions=[ExecutionResponse.from_execution(item) for item in manager.list_executions()]
    )


@router.get("/api/executions/{execution_id}", response_model=ExecutionResponse)
def get_execution(execution_id: UUID, manager: ExecutionManagerDependency) -> ExecutionResponse:
    """Return one execution snapshot."""
    try:
        return ExecutionResponse.from_execution(manager.get_execution(execution_id))
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/api/agents/{agent_id}/executions", response_model=ExecutionListResponse)
def list_agent_executions(
    agent_id: UUID, manager: ExecutionManagerDependency
) -> ExecutionListResponse:
    """Return one Agent's newest-first execution history."""
    return ExecutionListResponse(
        executions=[ExecutionResponse.from_execution(item) for item in manager.list_executions(agent_id)]
    )


@router.post("/api/executions/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(
    execution_id: UUID, manager: ExecutionManagerDependency
) -> ExecutionResponse:
    """Cancel a pending or active execution."""
    try:
        return ExecutionResponse.from_execution(await manager.cancel_execution(execution_id))
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ExecutionLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
