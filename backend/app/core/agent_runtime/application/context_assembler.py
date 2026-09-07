"""Minimal provider-neutral LLM context assembly for Agent interactions."""

from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.context import AgentContext
from backend.app.core.llm_runtime.domain.models import Message, MessageRole


class AgentContextAssembler:
    """Translate the currently supported Agent interaction state into LLM messages."""

    def assemble(
        self,
        agent: Agent,
        context: AgentContext,
        user_message: str,
    ) -> tuple[Message, ...]:
        """Return the current user turn; Agent Runtime has no conversation history yet."""
        del agent, context
        return (Message(role=MessageRole.USER, content=user_message),)
