"""REST adapters for workflow definitions and durable workflow runs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.api.dependencies.system import get_workflow_manager
from backend.app.core.api.schemas.workflows import (
    WorkflowCreateRequest,
    WorkflowDefinitionListResponse,
    WorkflowDefinitionResponse,
    WorkflowListResponse,
    WorkflowResponse,
    WorkflowRetryRequest,
    WorkflowRunCreateRequest,
    WorkflowTaskListResponse,
    WorkflowTaskResponse,
)
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.domain.exceptions import (
    WorkflowLifecycleError,
    WorkflowNotFoundError,
    WorkflowRetryError,
    WorkflowValidationError,
)
from backend.app.core.workflow_runtime.domain.models import Workflow

router = APIRouter(tags=["workflows"])
Manager = Annotated[WorkflowManager, Depends(get_workflow_manager)]


def response(manager: WorkflowManager, workflow: Workflow) -> WorkflowResponse:
    return WorkflowResponse.from_workflow(workflow, manager.retry_decision(workflow))


def error(caught: Exception) -> HTTPException:
    code = (
        status.HTTP_404_NOT_FOUND if isinstance(caught, WorkflowNotFoundError)
        else status.HTTP_409_CONFLICT if isinstance(caught, (WorkflowLifecycleError, WorkflowRetryError))
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return HTTPException(status_code=code, detail=str(caught))


# ------------------------------------------------------------------- definitions

@router.post("/api/workflow-definitions", response_model=WorkflowDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def create_definition(request: WorkflowCreateRequest, manager: Manager) -> WorkflowDefinitionResponse:
    try:
        definition = await manager.create_definition(name=request.name, description=request.description, tasks=tuple(t.to_task() for t in request.tasks), metadata=request.metadata)
    except (WorkflowValidationError, ValueError) as caught:
        raise error(caught) from caught
    return WorkflowDefinitionResponse.from_definition(definition)


@router.get("/api/workflow-definitions", response_model=WorkflowDefinitionListResponse)
async def list_definitions(manager: Manager) -> WorkflowDefinitionListResponse:
    return WorkflowDefinitionListResponse(definitions=[WorkflowDefinitionResponse.from_definition(d) for d in await manager.list_definitions()])


@router.get("/api/workflow-definitions/{definition_id}", response_model=WorkflowDefinitionResponse)
async def get_definition(definition_id: UUID, manager: Manager, version: Annotated[int | None, Query(ge=1)] = None) -> WorkflowDefinitionResponse:
    try:
        return WorkflowDefinitionResponse.from_definition(await manager.get_definition(definition_id, version))
    except WorkflowNotFoundError as caught:
        raise error(caught) from caught


@router.put("/api/workflow-definitions/{definition_id}", response_model=WorkflowDefinitionResponse)
async def update_definition(definition_id: UUID, request: WorkflowCreateRequest, manager: Manager) -> WorkflowDefinitionResponse:
    """Save a new version. Runs that already exist keep the version they started from."""
    try:
        definition = await manager.update_definition(definition_id, name=request.name, description=request.description, tasks=tuple(t.to_task() for t in request.tasks), metadata=request.metadata)
    except (WorkflowNotFoundError, WorkflowValidationError, ValueError) as caught:
        raise error(caught) from caught
    return WorkflowDefinitionResponse.from_definition(definition)


@router.post("/api/workflow-definitions/{definition_id}/runs", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_run(definition_id: UUID, request: WorkflowRunCreateRequest, manager: Manager) -> WorkflowResponse:
    try:
        return response(manager, await manager.create_run(definition_id, version=request.version, start=request.start))
    except WorkflowNotFoundError as caught:
        raise error(caught) from caught


# -------------------------------------------------------------------------- runs

@router.post("/api/workflows", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(request: WorkflowCreateRequest, manager: Manager) -> WorkflowResponse:
    """Define a workflow and create its first run (not started) in one call."""
    try:
        return response(manager, await manager.create(name=request.name, description=request.description, tasks=tuple(task.to_task() for task in request.tasks), metadata=request.metadata))
    except (WorkflowValidationError, ValueError) as caught:
        raise error(caught) from caught


@router.get("/api/workflows", response_model=WorkflowListResponse)
async def list_workflows(manager: Manager) -> WorkflowListResponse:
    return WorkflowListResponse(workflows=[response(manager, item) for item in await manager.list()])


@router.get("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: UUID, manager: Manager) -> WorkflowResponse:
    try:
        return response(manager, await manager.get(workflow_id))
    except WorkflowNotFoundError as caught:
        raise error(caught) from caught


@router.delete("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
async def delete_workflow(workflow_id: UUID, manager: Manager) -> WorkflowResponse:
    try:
        return response(manager, await manager.delete(workflow_id))
    except (WorkflowNotFoundError, WorkflowLifecycleError) as caught:
        raise error(caught) from caught


@router.post("/api/workflows/{workflow_id}/retry", response_model=WorkflowResponse)
async def retry_workflow(workflow_id: UUID, request: WorkflowRetryRequest, manager: Manager) -> WorkflowResponse:
    """Re-run unfinished steps of a failed or interrupted run; completed steps are kept."""
    try:
        return response(manager, await manager.retry(workflow_id, acknowledge_side_effects=request.acknowledge_side_effects))
    except (WorkflowNotFoundError, WorkflowLifecycleError, WorkflowRetryError) as caught:
        raise error(caught) from caught


@router.post("/api/workflows/{workflow_id}/{operation}", response_model=WorkflowResponse)
async def operate(workflow_id: UUID, operation: str, manager: Manager) -> WorkflowResponse:
    if operation not in {"start", "pause", "resume", "cancel"}:
        raise HTTPException(status_code=404, detail="Unknown workflow operation.")
    try:
        return response(manager, await getattr(manager, operation)(workflow_id))
    except (WorkflowNotFoundError, WorkflowLifecycleError) as caught:
        raise error(caught) from caught


@router.get("/api/workflows/{workflow_id}/tasks", response_model=WorkflowTaskListResponse)
async def workflow_tasks(workflow_id: UUID, manager: Manager) -> WorkflowTaskListResponse:
    try:
        return WorkflowTaskListResponse(tasks=[WorkflowTaskResponse.from_task(item) for item in await manager.history(workflow_id)])
    except WorkflowNotFoundError as caught:
        raise error(caught) from caught


@router.get("/api/workflows/{workflow_id}/history", response_model=WorkflowTaskListResponse)
async def workflow_history(workflow_id: UUID, manager: Manager) -> WorkflowTaskListResponse:
    return await workflow_tasks(workflow_id, manager)
