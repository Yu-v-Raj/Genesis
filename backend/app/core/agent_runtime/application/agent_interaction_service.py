"""Bounded Agent coordination across the LLM and Tool runtimes."""

import json
from dataclasses import replace
from uuid import UUID, uuid4

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.context_assembler import AgentContextAssembler
from backend.app.core.agent_runtime.application.tool_safety_gate import ToolSafetyGate
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.exceptions import AgentLifecycleError, AgentUnavailableError
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.agent_runtime.domain.interaction import InteractionSummary, ToolActivity
from backend.app.core.agent_runtime.domain.session import AgentSession
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.domain.exceptions import LLMConfigurationError
from backend.app.core.llm_runtime.domain.models import (
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus


class AgentInteractionService:
    """Coordinate an Agent's bounded LLM-to-Tool interaction loop."""

    DEFAULT_MAX_TOOL_ITERATIONS = 5

    def __init__(
        self,
        agent_registry: AgentRegistry,
        agent_manager: AgentManager,
        llm_manager: LLMManager,
        context_assembler: AgentContextAssembler | None = None,
        tool_manager: ToolRuntimeManager | None = None,
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    ) -> None:
        if max_tool_iterations < 1:
            raise ValueError("Maximum tool iterations must be positive.")
        self._agent_registry = agent_registry
        self._agent_manager = agent_manager
        self._llm_manager = llm_manager
        self._context_assembler = context_assembler or AgentContextAssembler()
        self._tool_manager = tool_manager
        self._max_tool_iterations = max_tool_iterations

    async def chat(self, agent_id: UUID, message: str, session_id: UUID | None = None) -> tuple[Agent, LLMResponse]:
        """Run an interaction while preserving the established two-value contract."""
        agent, response, _ = await self.chat_with_summary(agent_id, message, session_id)
        return agent, response

    async def chat_with_summary(
        self, agent_id: UUID, message: str, session_id: UUID | None = None
    ) -> tuple[Agent, LLMResponse, InteractionSummary]:
        """Run one IDLE Agent interaction and return its terminal record and LLM response.

        The turn's messages are committed to the session only when the interaction ends
        normally, so a failed request never leaves half a turn in the conversation.
        """
        agent = self._agent_registry.get(agent_id)
        interaction_id = uuid4()
        activities: list[ToolActivity] = []
        if agent.llm_model is None:
            raise LLMConfigurationError("This Agent has no model configured. Choose a model in its settings.")
        _require_available(agent)
        context = await self._agent_manager.get_context(agent_id)
        session = await self._agent_manager.get_session(agent_id, session_id)
        system_messages = self._context_assembler.system_messages(agent)
        turn = [
            _tagged(item, interaction_id)
            for item in self._context_assembler.assemble(agent, context, message)
        ]
        tools = self._tool_definitions(agent)
        try:
            await self._agent_manager.start_agent(agent_id, interaction_id=interaction_id)
        except AgentLifecycleError as error:
            raise AgentUnavailableError(_BUSY_MESSAGE) from error
        try:
            for _ in range(self._max_tool_iterations):
                response = await self._llm_manager.generate(
                    LLMRequest(
                        model=agent.llm_model,
                        messages=(*system_messages, *session.messages, *turn),
                        tools=tools,
                        metadata={"agent_id": str(agent.id), "interaction_id": str(interaction_id)},
                    )
                )
                turn.append(_tagged(self._assistant_tool_call_message(response), interaction_id))
                if not response.tool_calls:
                    await self._commit_turn(agent_id, session, turn)
                    return (
                        await self._agent_manager.finish_interaction(agent_id, interaction_id=interaction_id),
                        response,
                        InteractionSummary(
                            interaction_id=interaction_id,
                            session_id=session.id,
                            tool_activities=tuple(activities),
                        ),
                    )
                for tool_call in response.tool_calls:
                    tool_message, activity = await self._tool_result_message(agent, tool_call, interaction_id)
                    turn.append(_tagged(tool_message, interaction_id))
                    activities.append(activity)
            limit_response = LLMResponse(
                content="Tool-call iteration limit reached.",
                model=agent.llm_model,
                finish_reason="tool_iteration_limit",
                usage=response.usage,
                metadata={"tool_iteration_limit": self._max_tool_iterations},
            )
            turn.append(_tagged(self._assistant_tool_call_message(limit_response), interaction_id))
            await self._commit_turn(agent_id, session, turn)
        except Exception:
            await self._agent_manager.finish_interaction(agent_id, interaction_id=interaction_id)
            raise
        return (
            await self._agent_manager.finish_interaction(agent_id, interaction_id=interaction_id),
            limit_response,
            InteractionSummary(interaction_id=interaction_id, session_id=session.id, tool_activities=tuple(activities)),
        )

    async def _commit_turn(self, agent_id: UUID, session: AgentSession, turn: list[Message]) -> None:
        """Store the whole turn at once, only if nothing else extended the session meanwhile."""
        await self._agent_manager.append_session_messages(
            agent_id, session.id, *turn, expected_length=len(session.messages)
        )

    def _tool_definitions(self, agent: Agent) -> tuple[ToolDefinition, ...]:
        if self._tool_manager is None:
            return ()
        return tuple(
            ToolDefinition(
                name=tool.definition.name,
                description=tool.definition.description,
                parameters=tool.definition.parameters,
            )
            for tool in self._tool_manager.list_tools()
            if tool.name in agent.allowed_tools
        )

    @staticmethod
    def _assistant_tool_call_message(response: LLMResponse) -> Message:
        return Message(
            role=MessageRole.ASSISTANT,
            content=response.content or "",
            metadata={"tool_calls": response.tool_calls},
        )

    async def _tool_result_message(
        self, agent: Agent, tool_call: ToolCall, interaction_id: UUID
    ) -> tuple[Message, ToolActivity]:
        if self._tool_manager is None:
            result = ToolResult(
                tool_name=tool_call.name,
                result={"success": False, "error": "Tool runtime is unavailable."},
            )
            activity = ToolActivity(tool_name=tool_call.name, status="failed", error="Tool runtime is unavailable.")
        else:
            _, rejection, category = ToolSafetyGate(self._tool_manager).validate(
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                allowed_tools=agent.allowed_tools,
            )
            if rejection is not None:
                await self._agent_manager.publish_tool_rejected(
                    agent_id=agent.id, interaction_id=interaction_id, tool_name=tool_call.name, category=category or "unavailable"
                )
                result = ToolResult(
                    tool_name=tool_call.name,
                    result={"success": False, "error": rejection},
                )
                activity = ToolActivity(tool_name=tool_call.name, status="rejected", error=rejection)
            else:
                try:
                    task = await self._tool_manager.execute(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                        metadata={"agent_id": str(agent.id), "interaction_id": str(interaction_id)},
                    )
                    execution_result = task.result
                    if execution_result is None or execution_result.status is not ToolResultStatus.COMPLETED:
                        result = ToolResult(
                            tool_name=tool_call.name,
                            result={"success": False, "error": "Tool execution failed."},
                        )
                        activity = ToolActivity(
                            tool_name=tool_call.name,
                            status="failed",
                            error="Tool execution failed.",
                            duration=execution_result.duration,
                        )
                    else:
                        result = ToolResult(
                            tool_name=tool_call.name,
                            result={"success": True, "result": execution_result.output},
                        )
                        activity = ToolActivity(tool_name=tool_call.name, status="completed", result=execution_result.output, duration=execution_result.duration)
                except Exception:
                    result = ToolResult(
                        tool_name=tool_call.name,
                        result={"success": False, "error": "Tool execution failed."},
                    )
                    activity = ToolActivity(tool_name=tool_call.name, status="failed", error="Tool execution failed.")
        return Message(
            role=MessageRole.TOOL,
            content=json.dumps(result.result),
            metadata={
                "tool_call_id": tool_call.call_id,
                "tool_name": result.tool_name,
                "tool_status": activity.status,
            },
        ), activity


_BUSY_MESSAGE = "This Agent is already working on a request. Wait for it to finish, then try again."
_UNAVAILABLE_MESSAGES = {
    AgentStatus.RUNNING: _BUSY_MESSAGE,
    AgentStatus.CREATED: "This Agent isn't ready yet. Initialize it before chatting.",
    AgentStatus.INITIALIZING: "This Agent is still initializing. Try again in a moment.",
    AgentStatus.STOPPED: "This Agent is stopped and can no longer chat.",
}


def _require_available(agent: Agent) -> None:
    """Explain why a non-IDLE Agent cannot take a new message."""
    if agent.status is AgentStatus.IDLE:
        return
    raise AgentUnavailableError(
        _UNAVAILABLE_MESSAGES.get(agent.status, f"This Agent can't chat while it is {agent.status.value}.")
    )


def _tagged(message: Message, interaction_id: UUID) -> Message:
    """Record which interaction produced a session message."""
    return replace(message, metadata={**message.metadata, "interaction_id": str(interaction_id)})
