"""FastAPI adapter for Agent Runtime metadata and lifecycle operations."""

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.context import UNSET
from backend.app.core.agent_runtime.domain.exceptions import (
    AgentLifecycleError,
    AgentNotFoundError,
    DuplicateAgentError,
)
from backend.app.core.api.dependencies.system import get_agent_manager, get_agent_registry
from backend.app.core.api.schemas.agents import (
    AgentContextResponse,
    AgentContextUpdateRequest,
    AgentCountResponse,
    AgentCreateRequest,
    AgentListResponse,
    AgentMetadataUpdateRequest,
    AgentResponse,
)


router = APIRouter(prefix="/api/agents", tags=["agents"])
AgentRegistryDependency = Annotated[AgentRegistry, Depends(get_agent_registry)]
AgentManagerDependency = Annotated[AgentManager, Depends(get_agent_manager)]


@router.get("", response_model=AgentListResponse)
def list_agents(registry: AgentRegistryDependency) -> AgentListResponse:
    """Return all Agent Runtime records."""
    return AgentListResponse(agents=[AgentResponse.from_agent(agent) for agent in registry.list()])


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: AgentCreateRequest,
    manager: AgentManagerDependency,
) -> AgentResponse:
    """Create an Agent Runtime record without starting execution."""
    try:
        agent = await manager.create_agent(
            agent_id=request.id,
            name=request.name,
            description=request.description,
            type=request.type,
            metadata=request.metadata,
            tags=tuple(request.tags),
        )
    except DuplicateAgentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return AgentResponse.from_agent(agent)


@router.get("/count", response_model=AgentCountResponse)
def count_agents(registry: AgentRegistryDependency) -> AgentCountResponse:
    """Return the number of registered Agent Runtime records."""
    return AgentCountResponse(count=registry.count())


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: UUID, registry: AgentRegistryDependency) -> AgentResponse:
    """Return one Agent Runtime record by identifier."""
    try:
        return AgentResponse.from_agent(registry.get(agent_id))
    except AgentNotFoundError as error:
        raise _not_found(error) from error


@router.delete("/{agent_id}", response_model=AgentResponse)
async def delete_agent(agent_id: UUID, manager: AgentManagerDependency) -> AgentResponse:
    """Delete an Agent Runtime record and its ephemeral context."""
    try:
        return AgentResponse.from_agent(await manager.delete_agent(agent_id))
    except AgentNotFoundError as error:
        raise _not_found(error) from error


@router.post("/{agent_id}/initialize", response_model=AgentResponse)
async def initialize_agent(agent_id: UUID, manager: AgentManagerDependency) -> AgentResponse:
    """Synchronously initialize an Agent into its IDLE lifecycle state."""
    return AgentResponse.from_agent(await _lifecycle_operation(manager.initialize_agent, agent_id))


@router.post("/{agent_id}/start", response_model=AgentResponse)
async def start_agent(agent_id: UUID, manager: AgentManagerDependency) -> AgentResponse:
    """Move an initialized Agent into RUNNING."""
    return AgentResponse.from_agent(await _lifecycle_operation(manager.start_agent, agent_id))


@router.post("/{agent_id}/pause", response_model=AgentResponse)
async def pause_agent(agent_id: UUID, manager: AgentManagerDependency) -> AgentResponse:
    """Pause a RUNNING Agent."""
    return AgentResponse.from_agent(await _lifecycle_operation(manager.pause_agent, agent_id))


@router.post("/{agent_id}/resume", response_model=AgentResponse)
async def resume_agent(agent_id: UUID, manager: AgentManagerDependency) -> AgentResponse:
    """Resume a PAUSED Agent into RUNNING."""
    return AgentResponse.from_agent(await _lifecycle_operation(manager.resume_agent, agent_id))


@router.post("/{agent_id}/stop", response_model=AgentResponse)
async def stop_agent(agent_id: UUID, manager: AgentManagerDependency) -> AgentResponse:
    """Stop an Agent from any active lifecycle state."""
    return AgentResponse.from_agent(await _lifecycle_operation(manager.stop_agent, agent_id))


@router.patch("/{agent_id}/metadata", response_model=AgentResponse)
async def update_metadata(
    agent_id: UUID,
    request: AgentMetadataUpdateRequest,
    manager: AgentManagerDependency,
) -> AgentResponse:
    """Merge supplied values into persistent Agent metadata."""
    try:
        return AgentResponse.from_agent(await manager.update_metadata(agent_id, request.metadata))
    except AgentNotFoundError as error:
        raise _not_found(error) from error


@router.get("/{agent_id}/context", response_model=AgentContextResponse)
async def get_context(agent_id: UUID, manager: AgentManagerDependency) -> AgentContextResponse:
    """Return an Agent's ephemeral runtime context."""
    try:
        return AgentContextResponse.from_context(await manager.get_context(agent_id))
    except AgentNotFoundError as error:
        raise _not_found(error) from error


@router.patch("/{agent_id}/context", response_model=AgentContextResponse)
async def update_context(
    agent_id: UUID,
    request: AgentContextUpdateRequest,
    manager: AgentManagerDependency,
) -> AgentContextResponse:
    """Update ephemeral runtime context without changing Agent metadata."""
    try:
        context = await manager.update_context(
            agent_id,
            current_task=(request.current_task if "current_task" in request.model_fields_set else UNSET),
            temporary_variables=request.temporary_variables,
            runtime_metadata=request.runtime_metadata,
        )
    except AgentNotFoundError as error:
        raise _not_found(error) from error
    return AgentContextResponse.from_context(context)


async def _lifecycle_operation(
    operation: Callable[[UUID], Awaitable[Agent]],
    agent_id: UUID,
) -> Agent:
    """Translate lifecycle domain errors into stable HTTP responses."""
    try:
        return await operation(agent_id)
    except AgentNotFoundError as error:
        raise _not_found(error) from error
    except AgentLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


def _not_found(error: AgentNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
