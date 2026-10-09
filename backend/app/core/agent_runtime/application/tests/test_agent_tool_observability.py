"""Focused correlation and safe tool observability coverage."""

from collections.abc import Sequence

import pytest

from backend.app.core.agent_runtime.application.agent_interaction_service import AgentInteractionService
from backend.app.core.agent_runtime.application.agent_manager import AgentManager
from backend.app.core.agent_runtime.application.agent_registry import AgentRegistry
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.llm_manager import LLMManager
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall
from backend.app.core.observability.domain.events import Event
from backend.app.core.tool_runtime.application.tool_executor import ToolExecutor
from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager
from backend.app.core.tool_runtime.application.tool_registry import ToolRegistry
from backend.app.core.tool_runtime.domain.tool import builtin_tools


class ScriptedProvider(LLMProvider):
    def __init__(self, responses: Sequence[LLMResponse]) -> None:
        self._responses = iter(responses)

    @property
    def name(self) -> str:
        return "fake"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider=self.name, model_name="fake-1"),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return next(self._responses)


async def _service(responses: Sequence[LLMResponse], allowed_tools: tuple[str, ...] = ("calculator",)) -> tuple[AgentInteractionService, AgentManager, list[Event]]:
    event_bus = EventBus()
    events: list[Event] = []
    event_bus.subscribe(events.append)
    agent_registry = AgentRegistry(event_bus)
    manager = AgentManager(agent_registry, event_bus)
    tool_registry = ToolRegistry(event_bus)
    tool_manager = ToolRuntimeManager(tool_registry, ToolExecutor(tool_registry, event_bus), event_bus)
    for tool in builtin_tools():
        await tool_manager.register(tool)
    providers = LLMProviderRegistry()
    providers.register(ScriptedProvider(responses))
    agent = await manager.create_agent(
        name="assistant", description="Answers questions.", type="chat",
        llm_model=LLMModel(provider="fake", model_name="fake-1"), allowed_tools=allowed_tools,
    )
    await manager.initialize_agent(agent.id)
    return AgentInteractionService(agent_registry, manager, LLMManager(providers, event_bus), tool_manager=tool_manager), manager, events


@pytest.mark.asyncio
async def test_tool_interaction_events_share_a_safe_correlation_id() -> None:
    model = LLMModel(provider="fake", model_name="fake-1")
    service, manager, events = await _service((
        LLMResponse(content=None, model=model, tool_calls=(ToolCall(call_id="one", name="calculator", arguments={"expression": "2 + 3"}),)),
        LLMResponse(content="5", model=model),
    ))
    agent = manager._registry.list()[0]

    _, _, summary = await service.chat_with_summary(agent.id, "Calculate")

    related = [event for event in events if event.payload.get("interaction_id") == str(summary.interaction_id)]
    assert {event.event_type for event in related} >= {
        "agent.status_changed", "agent.started", "llm.requested", "llm.completed",
        "task.created", "task.completed", "tool.executed", "tool.completed",
    }
    assert summary.tool_activities[0].status == "completed"
    assert summary.tool_activities[0].result == 5


@pytest.mark.asyncio
async def test_safety_rejections_publish_only_safe_metadata() -> None:
    model = LLMModel(provider="fake", model_name="fake-1")
    service, manager, events = await _service((
        LLMResponse(content=None, model=model, tool_calls=(
            ToolCall(call_id="missing", name="missing", arguments={"secret": "do-not-broadcast"}),
            ToolCall(call_id="forbidden", name="echo", arguments={"message": "do-not-broadcast"}),
            ToolCall(call_id="invalid", name="calculator", arguments={"expression": 4}),
        )),
        LLMResponse(content="Handled", model=model),
    ))
    agent = manager._registry.list()[0]

    _, _, summary = await service.chat_with_summary(agent.id, "Try tools")

    rejected = [event for event in events if event.event_type == "tool.rejected"]
    assert [event.payload["category"] for event in rejected] == ["unavailable", "not_allowed", "invalid_arguments"]
    assert all(event.payload["agent_id"] == str(agent.id) for event in rejected)
    assert all(event.payload["interaction_id"] == str(summary.interaction_id) for event in rejected)
    assert all(set(event.payload) == {"agent_id", "interaction_id", "tool_name", "category"} for event in rejected)
    assert [activity.status for activity in summary.tool_activities] == ["rejected", "rejected", "rejected"]
