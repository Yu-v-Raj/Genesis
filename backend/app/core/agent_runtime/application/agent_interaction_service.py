"""Bounded Agent coordination across the LLM and Tool runtimes."""

import json
from uuid import UUID

from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.application.context_assembler import AgentContextAssembler
from backend.app.core.agent_runtime.application.tool_safety_gate import ToolSafetyGate
from backend.app.core.agent_runtime.domain.agent import Agent
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

    async def chat(self, agent_id: UUID, message: str) -> tuple[Agent, LLMResponse]:
        """Run one IDLE Agent interaction and return its terminal record and LLM response."""
        agent = self._agent_registry.get(agent_id)
        if agent.llm_model is None:
            raise LLMConfigurationError("Agent has no configured LLM model.")
        context = await self._agent_manager.get_context(agent_id)
        session = await self._agent_manager.get_session(agent_id)
        current_messages = self._context_assembler.assemble(agent, context, message)
        messages = [*session.messages, *current_messages]
        tools = self._tool_definitions(agent)
        await self._agent_manager.start_agent(agent_id)
        await self._agent_manager.append_session_messages(agent_id, *current_messages)
        try:
            for _ in range(self._max_tool_iterations):
                response = await self._llm_manager.generate(
                    LLMRequest(
                        model=agent.llm_model,
                        messages=tuple(messages),
                        tools=tools,
                    )
                )
                if not response.tool_calls:
                    assistant_message = self._assistant_tool_call_message(response)
                    await self._agent_manager.append_session_messages(agent_id, assistant_message)
                    return await self._agent_manager.finish_interaction(agent_id), response
                assistant_message = self._assistant_tool_call_message(response)
                messages.append(assistant_message)
                await self._agent_manager.append_session_messages(agent_id, assistant_message)
                for tool_call in response.tool_calls:
                    tool_message = await self._tool_result_message(agent, tool_call)
                    messages.append(tool_message)
                    await self._agent_manager.append_session_messages(agent_id, tool_message)
        except Exception:
            await self._agent_manager.finish_interaction(agent_id)
            raise
        return (
            await self._agent_manager.finish_interaction(agent_id),
            LLMResponse(
                content="Tool-call iteration limit reached.",
                model=agent.llm_model,
                finish_reason="tool_iteration_limit",
                usage=response.usage,
                metadata={"tool_iteration_limit": self._max_tool_iterations},
            ),
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

    async def _tool_result_message(self, agent: Agent, tool_call: ToolCall) -> Message:
        if self._tool_manager is None:
            result = ToolResult(
                tool_name=tool_call.name,
                result={"success": False, "error": "Tool runtime is unavailable."},
            )
        else:
            _, rejection = ToolSafetyGate(self._tool_manager).validate(
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                allowed_tools=agent.allowed_tools,
            )
            if rejection is not None:
                result = ToolResult(
                    tool_name=tool_call.name,
                    result={"success": False, "error": rejection},
                )
            else:
                try:
                    task = await self._tool_manager.execute(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                    )
                    execution_result = task.result
                    if execution_result is None or execution_result.status is not ToolResultStatus.COMPLETED:
                        result = ToolResult(
                            tool_name=tool_call.name,
                            result={"success": False, "error": "Tool execution failed."},
                        )
                    else:
                        result = ToolResult(
                            tool_name=tool_call.name,
                            result={"success": True, "result": execution_result.output},
                        )
                except Exception:
                    result = ToolResult(
                        tool_name=tool_call.name,
                        result={"success": False, "error": "Tool execution failed."},
                    )
        return Message(
            role=MessageRole.TOOL,
            content=json.dumps(result.result),
            metadata={"tool_call_id": tool_call.call_id, "tool_name": result.tool_name},
        )
