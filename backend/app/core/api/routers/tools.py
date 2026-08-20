"""REST adapters for Tool Runtime."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.api.dependencies.system import get_tool_runtime_manager
from backend.app.core.api.schemas.tools import ToolCapabilitiesResponse, ToolExecuteRequest, ToolHistoryResponse, ToolListResponse, ToolResponse, TaskResponse
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.exceptions import ToolNotFoundError


router = APIRouter(prefix="/api/tools", tags=["tools"])
ToolManagerDependency = Annotated[ToolRuntimeManager, Depends(get_tool_runtime_manager)]


@router.get("", response_model=ToolListResponse)
def list_tools(manager: ToolManagerDependency) -> ToolListResponse:
    return ToolListResponse(tools=[ToolResponse.from_tool(tool) for tool in manager.list_tools()])


@router.get("/history", response_model=ToolHistoryResponse)
def history(manager: ToolManagerDependency) -> ToolHistoryResponse:
    return ToolHistoryResponse(tasks=[TaskResponse.from_task(task) for task in manager.history()])


@router.get("/capabilities", response_model=ToolCapabilitiesResponse)
def capabilities(manager: ToolManagerDependency) -> ToolCapabilitiesResponse:
    return ToolCapabilitiesResponse(capabilities=list(manager.capabilities()))


@router.get("/{tool_name}", response_model=ToolResponse)
def get_tool(tool_name: str, manager: ToolManagerDependency) -> ToolResponse:
    try:
        return ToolResponse.from_tool(manager.get_tool(tool_name))
    except ToolNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.post("/execute", response_model=TaskResponse)
async def execute_tool(request: ToolExecuteRequest, manager: ToolManagerDependency) -> TaskResponse:
    task = await manager.execute(tool_name=request.tool_name, arguments=request.arguments, metadata=request.metadata, execution_id=request.execution_id)
    if task.result is not None and task.result.error is not None:
        status_code = status.HTTP_404_NOT_FOUND if "was not found" in task.result.error else status.HTTP_422_UNPROCESSABLE_CONTENT
        raise HTTPException(status_code=status_code, detail=task.result.error)
    return TaskResponse.from_task(task)
