"""FastAPI adapter for Agent Runtime metadata and lifecycle operations."""

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.agent_runtime.application.agent_configuration_service import AgentConfigurationService
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_interaction_service import AgentInteractionService
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.context import UNSET
from backend.app.core.agent_runtime.domain.exceptions import (
    AgentConfigurationError,
    AgentLifecycleError,
    AgentNotFoundError,
    AgentUnavailableError,
    DuplicateAgentError,
)
from backend.app.core.api.dependencies.system import (
    get_agent_configuration_service,
    get_agent_interaction_service,
    get_agent_manager,
    get_agent_registry,
)
from backend.app.core.api.schemas.agents import (
    AgentContextResponse,
    AgentContextUpdateRequest,
    AgentChatRequest,
    AgentChatResponse,
    AgentConfigurationUpdateRequest,
    AgentCountResponse,
    AgentCreateRequest,
    AgentListResponse,
    AgentMetadataUpdateRequest,
    AgentResponse,
    AgentSessionResponse,
)
from backend.app.core.llm_runtime.domain.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRuntimeError,
    LLMTimeoutError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)


router = APIRouter(prefix="/api/agents", tags=["agents"])
AgentRegistryDependency = Annotated[AgentRegistry, Depends(get_agent_registry)]
AgentManagerDependency = Annotated[AgentManager, Depends(get_agent_manager)]
AgentInteractionDependency = Annotated[
    AgentInteractionService, Depends(get_agent_interaction_service)
]
AgentConfigurationDependency = Annotated[
    AgentConfigurationService, Depends(get_agent_configuration_service)
]
# Since v0.10D, RUNNING means "an interaction is in progress" and is owned by chat.
# Manually entering it left Agents unable to chat, so these controls are retired.
_MANAGED_BY_INTERACTIONS = (
    "Agent activity is managed by conversations. Send the Agent a chat message instead; "
    "use stop to retire it."
)


@router.get("", response_model=AgentListResponse)
def list_agents(registry: AgentRegistryDependency) -> AgentListResponse:
    """Return all Agent Runtime records."""
    return AgentListResponse(agents=[AgentResponse.from_agent(agent) for agent in registry.list()])


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: AgentCreateRequest,
    configuration: AgentConfigurationDependency,
) -> AgentResponse:
    """Create a validated Agent, optionally initializing it so it can chat immediately."""
    try:
        agent = await configuration.create_agent(
            agent_id=request.id,
            name=request.name,
            description=request.description,
            type=request.type,
            metadata=request.metadata,
            tags=tuple(request.tags),
            llm_model=request.llm_model_domain(),
            allowed_tools=(None if request.allowed_tools is None else tuple(request.allowed_tools)),
            instructions=request.instructions,
            initialize=request.initialize,
        )
    except DuplicateAgentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except AgentConfigurationError as error:
        raise _invalid_configuration(error) from error
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


@router.post("/{agent_id}/start", response_model=AgentResponse, deprecated=True)
@router.post("/{agent_id}/pause", response_model=AgentResponse, deprecated=True)
@router.post("/{agent_id}/resume", response_model=AgentResponse, deprecated=True)
def retired_run_control(agent_id: UUID, registry: AgentRegistryDependency) -> AgentResponse:
    """Retired: interactions own RUNNING, so manual run controls are rejected."""
    if not registry.exists(agent_id):
        raise _not_found(AgentNotFoundError(agent_id))
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_MANAGED_BY_INTERACTIONS)


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


@router.patch("/{agent_id}/configuration", response_model=AgentResponse)
async def update_configuration(
    agent_id: UUID,
    request: AgentConfigurationUpdateRequest,
    configuration: AgentConfigurationDependency,
) -> AgentResponse:
    """Change an Agent's model, permitted tools, or instructions while it is not working."""
    fields = request.model_fields_set
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide llm_model, allowed_tools, or instructions to update.",
        )
    changes: dict[str, object] = {}
    if "llm_model" in fields:
        changes["llm_model"] = None if request.llm_model is None else request.llm_model.to_domain()
    if "allowed_tools" in fields:
        if request.allowed_tools is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="allowed_tools must be a list; use [] to allow no tools.",
            )
        changes["allowed_tools"] = tuple(request.allowed_tools)
    if "instructions" in fields:
        changes["instructions"] = request.instructions or ""
    try:
        agent = await configuration.update_configuration(agent_id, **changes)
    except AgentNotFoundError as error:
        raise _not_found(error) from error
    except AgentUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except AgentConfigurationError as error:
        raise _invalid_configuration(error) from error
    return AgentResponse.from_agent(agent)


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


@router.post("/{agent_id}/chat", response_model=AgentChatResponse)
async def chat(
    agent_id: UUID,
    request: AgentChatRequest,
    interaction: AgentInteractionDependency,
) -> AgentChatResponse:
    """Run one initialized Agent turn through the provider-neutral LLM Runtime."""
    try:
        agent, response, summary = await interaction.chat_with_summary(agent_id, request.message)
        return AgentChatResponse.from_domain(agent, response, summary)
    except AgentNotFoundError as error:
        raise _not_found(error) from error
    except AgentLifecycleError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ProviderNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except (LLMConfigurationError, ProviderUnavailableError) as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except LLMTimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(error)) from error
    except LLMProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except (LLMRuntimeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


@router.get("/{agent_id}/session", response_model=AgentSessionResponse)
async def get_session(agent_id: UUID, manager: AgentManagerDependency) -> AgentSessionResponse:
    try:
        return AgentSessionResponse.from_domain(await manager.get_session(agent_id))
    except AgentNotFoundError as error:
        raise _not_found(error) from error


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


def _invalid_configuration(error: AgentConfigurationError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))
