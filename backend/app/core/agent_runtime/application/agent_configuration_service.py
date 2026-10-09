"""Validated creation and reconfiguration of Agents against the live runtimes."""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.agent import MAX_INSTRUCTIONS_LENGTH, Agent
from backend.app.core.agent_runtime.domain.context import UNSET
from backend.app.core.agent_runtime.domain.exceptions import AgentConfigurationError
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.domain.models import LLMModel
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager


class AgentConfigurationService:
    """Reject configurations the LLM and Tool runtimes cannot honour before they are stored.

    Validation only checks what Genesis supports (registered providers, the models they
    expose, registered tools). A provider without credentials is still a valid choice: the
    Agent is stored and chat reports the missing credential when it is used.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        agent_manager: AgentManager,
        llm_manager: LLMManager,
        tool_manager: ToolRuntimeManager,
    ) -> None:
        self._agent_registry = agent_registry
        self._agent_manager = agent_manager
        self._llm_manager = llm_manager
        self._tool_manager = tool_manager

    async def create_agent(
        self,
        *,
        name: str,
        description: str,
        type: str,
        agent_id: UUID | None = None,
        metadata: Mapping[str, object] | None = None,
        tags: tuple[str, ...] = (),
        llm_model: LLMModel | None = None,
        allowed_tools: tuple[str, ...] | None = None,
        instructions: str = "",
        initialize: bool = False,
    ) -> Agent:
        """Validate configuration, create the Agent, and optionally make it ready to chat."""
        self.validate(llm_model=llm_model, allowed_tools=allowed_tools, instructions=instructions)
        agent = await self._agent_manager.create_agent(
            name=name,
            description=description,
            type=type,
            agent_id=agent_id,
            metadata=metadata,
            tags=tags,
            llm_model=llm_model,
            allowed_tools=None if allowed_tools is None else _unique(allowed_tools),
            instructions=instructions,
        )
        if initialize:
            agent = await self._agent_manager.initialize_agent(agent.id)
        return agent

    async def update_configuration(
        self,
        agent_id: UUID,
        *,
        llm_model: LLMModel | None | object = UNSET,
        allowed_tools: tuple[str, ...] | object = UNSET,
        instructions: str | object = UNSET,
    ) -> Agent:
        """Apply a partial configuration change; omitted fields keep their current values."""
        current = self._agent_registry.get(agent_id)
        model = current.llm_model if llm_model is UNSET else cast(LLMModel | None, llm_model)
        tools = (
            current.allowed_tools
            if allowed_tools is UNSET
            else _unique(cast(tuple[str, ...], allowed_tools))
        )
        text = current.instructions if instructions is UNSET else cast(str, instructions)
        self.validate(llm_model=model, allowed_tools=tools, instructions=text)
        return await self._agent_manager.update_configuration(
            agent_id, llm_model=model, allowed_tools=tools, instructions=text
        )

    def validate(
        self,
        *,
        llm_model: LLMModel | None,
        allowed_tools: tuple[str, ...] | None,
        instructions: str,
    ) -> None:
        """Raise ``AgentConfigurationError`` describing the first invalid setting."""
        if llm_model is not None:
            providers = self._llm_manager.providers()
            if llm_model.provider not in providers:
                raise AgentConfigurationError(
                    "llm_model",
                    f"Unknown LLM provider '{llm_model.provider}'. "
                    f"Available providers: {', '.join(providers) or 'none'}.",
                )
            models = [
                model.model_name
                for model in self._llm_manager.models()
                if model.provider == llm_model.provider
            ]
            if llm_model.model_name not in models:
                raise AgentConfigurationError(
                    "llm_model",
                    f"Model '{llm_model.model_name}' is not available from {llm_model.provider}. "
                    f"Available models: {', '.join(models) or 'none'}.",
                )
        if allowed_tools is not None:
            registered = {tool.name for tool in self._tool_manager.list_tools()}
            unknown = [name for name in _unique(allowed_tools) if name not in registered]
            if unknown:
                raise AgentConfigurationError(
                    "allowed_tools",
                    f"Unknown tools: {', '.join(unknown)}. "
                    f"Available tools: {', '.join(sorted(registered)) or 'none'}.",
                )
        if len(instructions) > MAX_INSTRUCTIONS_LENGTH:
            raise AgentConfigurationError(
                "instructions",
                f"Instructions must be at most {MAX_INSTRUCTIONS_LENGTH} characters.",
            )


def _unique(names: tuple[str, ...]) -> tuple[str, ...]:
    """Drop duplicate tool names while keeping the caller's order."""
    return tuple(dict.fromkeys(names))
