"""FastAPI adapter for agent-scoped Memory Runtime records."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.api.dependencies.system import get_agent_registry, get_memory_manager
from backend.app.core.api.schemas.memory import MemoryCreateRequest, MemoryListResponse, MemoryResponse, MemoryUpdateRequest
from backend.app.core.memory.application.memory_manager import MemoryManager
from backend.app.core.memory.domain.exceptions import MemoryNotFoundError, MemoryOwnershipError

router = APIRouter(tags=["memory"])
Manager = Annotated[MemoryManager, Depends(get_memory_manager)]
Registry = Annotated[AgentRegistry, Depends(get_agent_registry)]

def agent(registry: AgentRegistry, agent_id: UUID) -> None:
    if not registry.exists(agent_id): raise HTTPException(status_code=404, detail=f"Agent {agent_id} was not found.")
def not_found(error: Exception) -> HTTPException: return HTTPException(status_code=404, detail=str(error))

@router.get("/api/memory", response_model=MemoryListResponse)
async def list_memory(manager: Manager) -> MemoryListResponse: return MemoryListResponse(memories=[MemoryResponse.from_memory(item) for item in await manager.list_memories()])
@router.get("/api/memory/{memory_id}", response_model=MemoryResponse)
async def get_memory(memory_id: UUID, manager: Manager) -> MemoryResponse:
    try: return MemoryResponse.from_memory(await manager.get_memory(memory_id))
    except MemoryNotFoundError as error: raise not_found(error) from error
@router.patch("/api/memory/{memory_id}", response_model=MemoryResponse)
async def update_memory(memory_id: UUID, request: MemoryUpdateRequest, manager: Manager) -> MemoryResponse:
    if not request.model_fields_set: raise HTTPException(status_code=422, detail="At least one memory field is required.")
    try: return MemoryResponse.from_memory(await manager.update_memory(memory_id, content=request.content if "content" in request.model_fields_set else None, kind=request.kind if "kind" in request.model_fields_set else None, metadata=request.metadata if "metadata" in request.model_fields_set else None, tags=None if "tags" not in request.model_fields_set else tuple(request.tags or [])))
    except MemoryNotFoundError as error: raise not_found(error) from error
@router.delete("/api/memory/{memory_id}", response_model=MemoryResponse)
async def delete_memory(memory_id: UUID, manager: Manager) -> MemoryResponse:
    try: return MemoryResponse.from_memory(await manager.delete_memory(memory_id))
    except MemoryNotFoundError as error: raise not_found(error) from error
@router.get("/api/agents/{agent_id}/memory", response_model=MemoryListResponse)
async def list_agent_memory(agent_id: UUID, manager: Manager, registry: Registry) -> MemoryListResponse:
    agent(registry, agent_id); return MemoryListResponse(memories=[MemoryResponse.from_memory(item) for item in await manager.list_memories(agent_id)])
@router.post("/api/agents/{agent_id}/memory", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(agent_id: UUID, request: MemoryCreateRequest, manager: Manager, registry: Registry) -> MemoryResponse:
    agent(registry, agent_id); return MemoryResponse.from_memory(await manager.create_memory(agent_id=agent_id, content=request.content, kind=request.kind, metadata=request.metadata, tags=tuple(request.tags)))
@router.get("/api/agents/{agent_id}/memory/search", response_model=MemoryListResponse)
async def search_memory(agent_id: UUID, manager: Manager, registry: Registry, query: str = Query(min_length=1)) -> MemoryListResponse:
    agent(registry, agent_id); return MemoryListResponse(memories=[MemoryResponse.from_memory(item) for item in await manager.search_memories(agent_id, query)])
