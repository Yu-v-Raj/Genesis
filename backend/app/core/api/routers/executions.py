"""FastAPI adapter for durable Execution Runtime operations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.agent_runtime.domain.exceptions import AgentNotFoundError
from backend.app.core.api.dependencies.system import get_execution_manager
from backend.app.core.api.schemas.executions import (
    ExecutionCreateRequest,
    ExecutionHistoryResponse,
    ExecutionListResponse,
    ExecutionResponse,
    ExecutionRetryRequest,
    ExecutionTransitionResponse,
)
from backend.app.core.execution_runtime.application.execution_manager import ExecutionManager
from backend.app.core.execution_runtime.domain.exceptions import (
    AgentNotExecutableError,
    ExecutionLifecycleError,
    ExecutionNotFoundError,
    ExecutionRetryError,
)
from backend.app.core.execution_runtime.domain.execution import Execution


router = APIRouter(tags=["executions"])
ExecutionManagerDependency = Annotated[ExecutionManager, Depends(get_execution_manager)]


def _response(manager: ExecutionManager, execution: Execution) -> ExecutionResponse:
    return ExecutionResponse.from_execution(execution, manager.retry_decision(execution))


@router.post("/api/agents/{agent_id}/execute", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute_agent(
    agent_id: UUID,
    request: ExecutionCreateRequest,
    manager: ExecutionManagerDependency,
) -> ExecutionResponse:
    """Durably queue work for an initialized Agent."""
    try:
        return _response(manager, await manager.execute(agent_id, metadata=request.metadata))
    except AgentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except AgentNotExecutableError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get("/api/executions", response_model=ExecutionListResponse)
async def list_executions(manager: ExecutionManagerDependency) -> ExecutionListResponse:
    """Return recent executions, newest first."""
    return ExecutionListResponse(executions=[_response(manager, item) for item in await manager.list_executions()])


@router.get("/api/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: UUID, manager: ExecutionManagerDependency) -> ExecutionResponse:
    try:
        return _response(manager, await manager.get_execution(execution_id))
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/api/executions/{execution_id}/history", response_model=ExecutionHistoryResponse)
async def get_execution_history(execution_id: UUID, manager: ExecutionManagerDependency) -> ExecutionHistoryResponse:
    """Return the durable, ordered state timeline of one execution."""
    try:
        transitions = await manager.execution_history(execution_id)
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return ExecutionHistoryResponse(
        execution_id=execution_id,
        transitions=[ExecutionTransitionResponse.from_domain(item) for item in transitions],
    )


@router.get("/api/agents/{agent_id}/executions", response_model=ExecutionListResponse)
async def list_agent_executions(agent_id: UUID, manager: ExecutionManagerDependency) -> ExecutionListResponse:
    return ExecutionListResponse(executions=[_response(manager, item) for item in await manager.list_executions(agent_id)])


@router.post("/api/executions/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(execution_id: UUID, manager: ExecutionManagerDependency) -> ExecutionResponse:
    """Cancel a pending or active execution."""
    try:
        return _response(manager, await manager.cancel_execution(execution_id))
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except ExecutionLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/api/executions/{execution_id}/retry", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
async def retry_execution(
    execution_id: UUID,
    request: ExecutionRetryRequest,
    manager: ExecutionManagerDependency,
) -> ExecutionResponse:
    """Queue a new attempt of failed, cancelled, or interrupted work.

    Interrupted work that may have had external effects is only retried when the caller
    sets ``acknowledge_side_effects``; otherwise the response is 409 with the reason.
    """
    try:
        return _response(
            manager,
            await manager.retry_execution(execution_id, acknowledge_side_effects=request.acknowledge_side_effects),
        )
    except ExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except AgentNotExecutableError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ExecutionRetryError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
