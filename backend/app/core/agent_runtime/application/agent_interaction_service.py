"""Single-turn Agent to LLM Runtime interaction orchestration."""

from uuid import UUID

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.context_assembler import AgentContextAssembler
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.domain.exceptions import LLMConfigurationError
from backend.app.core.llm_runtime.domain.models import LLMRequest, LLMResponse


class AgentInteractionService:
    """Coordinate exactly one existing Agent lifecycle turn through ``LLMManager``."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        agent_manager: AgentManager,
        llm_manager: LLMManager,
        context_assembler: AgentContextAssembler | None = None,
    ) -> None:
        self._agent_registry = agent_registry
        self._agent_manager = agent_manager
        self._llm_manager = llm_manager
        self._context_assembler = context_assembler or AgentContextAssembler()

    async def chat(self, agent_id: UUID, message: str) -> tuple[Agent, LLMResponse]:
        """Run one IDLE Agent interaction and return its terminal record and LLM response."""
        agent = self._agent_registry.get(agent_id)
        if agent.llm_model is None:
            raise LLMConfigurationError("Agent has no configured LLM model.")
        context = await self._agent_manager.get_context(agent_id)
        messages = self._context_assembler.assemble(agent, context, message)
        await self._agent_manager.start_agent(agent_id)
        try:
            response = await self._llm_manager.generate(
                LLMRequest(model=agent.llm_model, messages=messages)
            )
        except Exception:
            await self._agent_manager.fail_agent(agent_id)
            raise
        return await self._agent_manager.complete_agent(agent_id), response
