from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.api.dependencies.system import get_workflow_manager
from backend.app.core.api.schemas.workflows import WorkflowCreateRequest, WorkflowListResponse, WorkflowResponse, WorkflowTaskListResponse, WorkflowTaskResponse
from backend.app.core.workflow_runtime.application.workflow_manager import WorkflowManager
from backend.app.core.workflow_runtime.domain.exceptions import WorkflowLifecycleError, WorkflowNotFoundError, WorkflowValidationError

router = APIRouter(tags=["workflows"])
Manager = Annotated[WorkflowManager, Depends(get_workflow_manager)]

def response(workflow): return WorkflowResponse.from_workflow(workflow)
def error(caught: Exception) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(caught, WorkflowNotFoundError) else status.HTTP_409_CONFLICT if isinstance(caught, WorkflowLifecycleError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(caught))

@router.post("/api/workflows", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(request: WorkflowCreateRequest, manager: Manager):
    try: return response(await manager.create(name=request.name, description=request.description, tasks=tuple(task.to_task() for task in request.tasks), metadata=request.metadata))
    except (WorkflowValidationError, ValueError) as caught: raise error(caught) from caught
@router.get("/api/workflows", response_model=WorkflowListResponse)
def list_workflows(manager: Manager): return WorkflowListResponse(workflows=[response(item) for item in manager.list()])
@router.get("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: UUID, manager: Manager):
    try: return response(manager.get(workflow_id))
    except WorkflowNotFoundError as caught: raise error(caught) from caught
@router.delete("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
async def delete_workflow(workflow_id: UUID, manager: Manager):
    try: return response(await manager.delete(workflow_id))
    except (WorkflowNotFoundError, WorkflowLifecycleError) as caught: raise error(caught) from caught
@router.post("/api/workflows/{workflow_id}/{operation}", response_model=WorkflowResponse)
async def operate(workflow_id: UUID, operation: str, manager: Manager):
    if operation not in {"start", "pause", "resume", "cancel"}: raise HTTPException(status_code=404, detail="Unknown workflow operation.")
    try: return response(await getattr(manager, operation)(workflow_id))
    except (WorkflowNotFoundError, WorkflowLifecycleError) as caught: raise error(caught) from caught
@router.get("/api/workflows/{workflow_id}/tasks", response_model=WorkflowTaskListResponse)
def workflow_tasks(workflow_id: UUID, manager: Manager):
    try: return WorkflowTaskListResponse(tasks=[WorkflowTaskResponse.from_task(item) for item in manager.history(workflow_id)])
    except WorkflowNotFoundError as caught: raise error(caught) from caught
@router.get("/api/workflows/{workflow_id}/history", response_model=WorkflowTaskListResponse)
def workflow_history(workflow_id: UUID, manager: Manager): return workflow_tasks(workflow_id, manager)
