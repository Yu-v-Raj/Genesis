"""Focused coverage for Agent Runtime's bounded tool coordination loop."""

import json
from collections.abc import Sequence

import pytest

from backend.app.core.agent_runtime.application.agent_interaction_service import (
    AgentInteractionService,
)
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.agent_runtime.domain.agent import Agent
from backend.app.core.agent_runtime.domain.status import AgentStatus
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import builtin_tools


class ScriptedProvider(LLMProvider):
    def __init__(self, responses: Sequence[LLMResponse]) -> None:
        self._responses = iter(responses)
        self.requests: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider=self.name, model_name="fake-1"),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return next(self._responses)


async def service_with_responses(
    responses: Sequence[LLMResponse], *, max_tool_iterations: int = 5
) -> tuple[AgentManager, AgentInteractionService, ScriptedProvider]:
    event_bus = EventBus()
    registry = AgentRegistry(event_bus)
    agent_manager = AgentManager(registry, event_bus)
    tool_registry = ToolRegistry(event_bus)
    tool_manager = ToolRuntimeManager(tool_registry, ToolExecutor(tool_registry, event_bus), event_bus)
    for tool in builtin_tools():
        await tool_manager.register(tool)
    provider = ScriptedProvider(responses)
    providers = LLMProviderRegistry()
    providers.register(provider)
    return (
        agent_manager,
        AgentInteractionService(
            registry,
            agent_manager,
            LLMManager(providers, event_bus),
            tool_manager=tool_manager,
            max_tool_iterations=max_tool_iterations,
        ),
        provider,
    )


async def initialized_agent(manager: AgentManager) -> Agent:
    agent = await manager.create_agent(
        name="assistant",
        description="Answers questions.",
        type="chat",
        llm_model=LLMModel(provider="fake", model_name="fake-1"),
    )
    await manager.initialize_agent(agent.id)
    return agent


@pytest.mark.asyncio
async def test_agent_executes_tool_and_feeds_result_back_to_llm() -> None:
    model = LLMModel(provider="fake", model_name="fake-1")
    manager, service, provider = await service_with_responses(
        (
            LLMResponse(
                content=None,
                model=model,
                tool_calls=(
                    ToolCall(
                        call_id="call-1",
                        name="calculator",
                        arguments={"expression": "25 * 4"},
                    ),
                ),
            ),
            LLMResponse(content="100", model=model),
        )
    )
    agent = await initialized_agent(manager)

    completed, response = await service.chat(agent.id, "What is 25 * 4?")

    assert completed.status is AgentStatus.COMPLETED
    assert response.content == "100"
    assert provider.requests[0].tools[1].name == "calculator"
    assert provider.requests[1].messages[1].metadata["tool_calls"][0].name == "calculator"
    assert json.loads(provider.requests[1].messages[2].content) == {
        "success": True,
        "result": 100,
    }


@pytest.mark.asyncio
async def test_agent_executes_multiple_tool_calls_sequentially() -> None:
    model = LLMModel(provider="fake", model_name="fake-1")
    manager, service, provider = await service_with_responses(
        (
            LLMResponse(
                content=None,
                model=model,
                tool_calls=(
                    ToolCall(call_id="one", name="calculator", arguments={"expression": "2 + 2"}),
                    ToolCall(call_id="two", name="echo", arguments={"message": "done"}),
                ),
            ),
            LLMResponse(content="4 and done", model=model),
        )
    )
    agent = await initialized_agent(manager)

    _, response = await service.chat(agent.id, "Use two tools")

    assert response.content == "4 and done"
    assert [message.role.value for message in provider.requests[1].messages] == [
        "user",
        "assistant",
        "tool",
        "tool",
    ]


@pytest.mark.asyncio
async def test_unknown_tool_is_returned_as_a_safe_result() -> None:
    model = LLMModel(provider="fake", model_name="fake-1")
    manager, service, provider = await service_with_responses(
        (
            LLMResponse(
                content=None,
                model=model,
                tool_calls=(ToolCall(call_id="missing", name="missing_tool"),),
            ),
            LLMResponse(content="I cannot use that tool.", model=model),
        )
    )
    agent = await initialized_agent(manager)

    _, response = await service.chat(agent.id, "Try an unknown tool")

    assert response.content == "I cannot use that tool."
    assert json.loads(provider.requests[1].messages[2].content) == {
        "success": False,
        "error": "Tool execution failed.",
    }


@pytest.mark.asyncio
async def test_tool_iteration_limit_stops_repeated_tool_calls() -> None:
    model = LLMModel(provider="fake", model_name="fake-1")
    repeated_call = LLMResponse(
        content=None,
        model=model,
        tool_calls=(ToolCall(call_id="loop", name="echo", arguments={"message": "again"}),),
    )
    manager, service, provider = await service_with_responses(
        (repeated_call, repeated_call), max_tool_iterations=2
    )
    agent = await initialized_agent(manager)

    failed, response = await service.chat(agent.id, "Loop")

    assert failed.status is AgentStatus.FAILED
    assert response.finish_reason == "tool_iteration_limit"
    assert len(provider.requests) == 2
