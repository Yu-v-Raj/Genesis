"""Unit tests for provider-neutral OpenAI request translation."""

from backend.app.core.llm_runtime.domain.models import (
    LLMModel,
    LLMRequest,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
)
from backend.app.core.llm_runtime.infrastructure.openai_provider import OpenAIProvider


def test_tools_payload_translates_provider_neutral_definition() -> None:
    request = LLMRequest(
        model=LLMModel(provider="openai", model_name="gpt-test"),
        messages=(Message(role=MessageRole.USER, content="calculate"),),
        tools=(
            ToolDefinition(
                name="calculator",
                description="Perform arithmetic calculations.",
                parameters={"type": "object", "properties": {"expression": {"type": "string"}}},
            ),
        ),
    )

    assert OpenAIProvider._tools_payload(request) == [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Perform arithmetic calculations.",
                "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}},
            },
        }
    ]


def test_messages_payload_maps_tool_call_and_result_conversation() -> None:
    request = LLMRequest(
        model=LLMModel(provider="openai", model_name="gpt-test"),
        messages=(
            Message(role=MessageRole.USER, content="What is 25 * 4?"),
            Message(
                role=MessageRole.ASSISTANT,
                content="",
                metadata={
                    "tool_calls": (
                        ToolCall(
                            call_id="call-1",
                            name="calculator",
                            arguments={"expression": "25 * 4"},
                        ),
                    )
                },
            ),
            Message(
                role=MessageRole.TOOL,
                content='{"success": true, "result": 100}',
                metadata={"tool_call_id": "call-1", "tool_name": "calculator"},
            ),
        ),
    )

    assert OpenAIProvider._messages_payload(request) == [
        {"role": "user", "content": "What is 25 * 4?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "calculator",
                        "arguments": '{"expression": "25 * 4"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": '{"success": true, "result": 100}',
            "tool_call_id": "call-1",
        },
    ]
