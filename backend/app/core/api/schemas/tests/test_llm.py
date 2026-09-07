"""Tests for the LLM REST schema's optional tool definitions."""

from backend.app.core.api.schemas.llm import GenerateRequest


def test_generate_request_defaults_tools_to_empty() -> None:
    request = GenerateRequest.model_validate(
        {
            "model": {"provider": "gemini", "model_name": "gemini-test"},
            "messages": [{"role": "user", "content": "Hello"}],
        }
    )

    assert request.to_domain().tools == ()


def test_generate_request_translates_tool_definitions() -> None:
    request = GenerateRequest.model_validate(
        {
            "model": {"provider": "gemini", "model_name": "gemini-test"},
            "messages": [{"role": "user", "content": "Calculate"}],
            "tools": [
                {
                    "name": "calculator",
                    "description": "Perform arithmetic calculations.",
                    "parameters": {"type": "object"},
                }
            ],
        }
    )

    tool = request.to_domain().tools[0]
    assert tool.name == "calculator"
    assert tool.parameters == {"type": "object"}
