"""Unit tests for provider-neutral OpenAI request translation."""

from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, Message, MessageRole, ToolDefinition
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
