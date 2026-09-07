"""Focused tests for provider-neutral tool-calling records."""

import pytest

from backend.app.core.llm_runtime.domain.models import (
    LLMModel,
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


def calculator() -> ToolDefinition:
    return ToolDefinition(
        name="calculator",
        description="Perform arithmetic calculations.",
        parameters={"type": "object", "properties": {"expression": {"type": "string"}}},
    )


def test_tool_definition_is_validated_and_immutable() -> None:
    definition = calculator()

    assert definition.name == "calculator"
    assert definition.parameters["type"] == "object"
    with pytest.raises(TypeError):
        definition.parameters["type"] = "array"  # type: ignore[index]


def test_tool_call_and_result_are_provider_neutral_records() -> None:
    call = ToolCall(call_id="call-1", name="calculator", arguments={"expression": "25 * 4"})
    result = ToolResult(tool_name="calculator", result="100")

    assert call.name == result.tool_name == "calculator"
    assert call.arguments == {"expression": "25 * 4"}
    assert result.result == "100"


def test_request_tools_and_response_tool_calls_default_to_empty() -> None:
    model = LLMModel(provider="fake", model_name="fake-1")
    request = LLMRequest(
        model=model,
        messages=(Message(role=MessageRole.USER, content="calculate"),),
        tools=(calculator(),),
    )
    response = LLMResponse(content="done", model=model)

    assert request.tools == (calculator(),)
    assert response.tool_calls == ()


def test_response_accepts_tool_calls_without_content() -> None:
    model = LLMModel(provider="fake", model_name="fake-1")
    response = LLMResponse(
        content=None,
        model=model,
        tool_calls=(ToolCall(call_id="call-1", name="calculator", arguments={"expression": "25 * 4"}),),
    )

    assert response.content is None
    assert response.tool_calls[0].arguments == {"expression": "25 * 4"}
