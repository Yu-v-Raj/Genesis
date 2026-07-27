"""Read-only FastAPI adapter for the Genesis Agent Runtime registry."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.exceptions import AgentNotFoundError
from backend.app.core.api.dependencies.system import get_agent_registry
from backend.app.core.api.schemas.agents import AgentCountResponse, AgentListResponse, AgentResponse


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
def list_agents(
    registry: Annotated[AgentRegistry, Depends(get_agent_registry)],
) -> AgentListResponse:
    """Return all Agent Runtime records."""
    return AgentListResponse(agents=[AgentResponse.from_agent(agent) for agent in registry.list()])


@router.get("/count", response_model=AgentCountResponse)
def count_agents(
    registry: Annotated[AgentRegistry, Depends(get_agent_registry)],
) -> AgentCountResponse:
    """Return the number of registered Agent Runtime records."""
    return AgentCountResponse(count=registry.count())


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: UUID,
    registry: Annotated[AgentRegistry, Depends(get_agent_registry)],
) -> AgentResponse:
    """Return one Agent Runtime record by identifier."""
    try:
        return AgentResponse.from_agent(registry.get(agent_id))
    except AgentNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
