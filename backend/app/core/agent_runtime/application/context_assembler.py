"""Minimal provider-neutral LLM context assembly for Agent interactions."""

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.context import AgentContext
from backend.app.core.llm_runtime.domain.models import Message, MessageRole


class AgentContextAssembler:
    """Translate the currently supported Agent interaction state into LLM messages."""

    def system_messages(self, agent: Agent) -> tuple[Message, ...]:
        """Return the Agent's standing instructions; they are not stored in the session."""
        instructions = agent.instructions.strip()
        if not instructions:
            return ()
        return (Message(role=MessageRole.SYSTEM, content=instructions),)

    def assemble(
        self,
        agent: Agent,
        context: AgentContext,
        user_message: str,
    ) -> tuple[Message, ...]:
        """Return the current user turn; session history is prepended by the caller."""
        del agent, context
        return (Message(role=MessageRole.USER, content=user_message),)
