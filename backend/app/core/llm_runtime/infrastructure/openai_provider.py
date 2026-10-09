"""OpenAI SDK adapter; SDK specifics remain isolated here."""

import asyncio
import json
from typing import Any

from backend.app.core.core_services.config.settings import Settings
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.domain.exceptions import LLMConfigurationError, LLMProviderError, LLMResponseNormalizationError, LLMTimeoutError
from backend.app.core.llm_runtime.domain.models import (
    LLMModel,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ToolCall,
    Usage,
)


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.OPENAI_API_KEY.get_secret_value() if settings.OPENAI_API_KEY else None
        self._model = settings.OPENAI_MODEL
        self._timeout = settings.OPENAI_TIMEOUT_SECONDS

    @property
    def name(self) -> str:
        return "openai"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider=self.name, model_name=self._model, capabilities=frozenset({"chat"}), metadata={"configured": self._api_key is not None}),)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key:
            raise LLMConfigurationError("OpenAI is not configured: OPENAI_API_KEY is required.")
        if request.model.provider != self.name:
            raise LLMProviderError("OpenAIProvider received a request for another provider.")
        try:
            from openai import AsyncOpenAI
        except ImportError as error:
            raise LLMConfigurationError("OpenAI support requires the optional 'openai' package.") from error
        try:
            client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)
            completion = await client.chat.completions.create(
                model=request.model.model_name,
                messages=self._messages_payload(request),
                temperature=request.generation.temperature,
                max_tokens=request.generation.max_tokens,
                tools=self._tools_payload(request),
            )
            choice = completion.choices[0]
            usage = completion.usage
            return LLMResponse(content=choice.message.content, model=request.model, finish_reason=choice.finish_reason, usage=Usage(input_tokens=None if usage is None else usage.prompt_tokens, output_tokens=None if usage is None else usage.completion_tokens, total_tokens=None if usage is None else usage.total_tokens), tool_calls=tuple(self._tool_call(item) for item in (choice.message.tool_calls or ())), metadata={})
        except asyncio.TimeoutError as error:
            raise LLMTimeoutError("OpenAI generation timed out.") from error
        except (IndexError, AttributeError, TypeError, ValueError) as error:
            raise LLMResponseNormalizationError("OpenAI returned a response Genesis could not normalize.") from error
        except LLMProviderError:
            raise
        except Exception as error:
            raise LLMProviderError("OpenAI generation failed.") from error

    @staticmethod
    def _messages_payload(request: LLMRequest) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for message in request.messages:
            if message.role is MessageRole.ASSISTANT and message.metadata.get("tool_calls"):
                tool_calls = []
                for tool_call in message.metadata["tool_calls"]:
                    if not isinstance(tool_call, ToolCall):
                        raise ValueError("Assistant tool-call metadata is invalid.")
                    tool_calls.append(
                        {
                            "id": tool_call.call_id,
                            "type": "function",
                            "function": {
                                "name": tool_call.name,
                                "arguments": json.dumps(dict(tool_call.arguments)),
                            },
                        }
                    )
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or None,
                        "tool_calls": tool_calls,
                    }
                )
                continue
            if message.role is MessageRole.TOOL and "tool_call_id" in message.metadata:
                call_id = message.metadata.get("tool_call_id")
                if not isinstance(call_id, str) or not call_id:
                    raise ValueError("Tool result metadata requires a tool-call ID.")
                messages.append(
                    {
                        "role": "tool",
                        "content": message.content,
                        "tool_call_id": call_id,
                    }
                )
                continue
            messages.append({"role": message.role.value, "content": message.content})
        return messages

    @staticmethod
    def _tools_payload(request: LLMRequest) -> list[dict[str, object]] | None:
        if not request.tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": dict(tool.parameters),
                },
            }
            for tool in request.tools
        ]

    @staticmethod
    def _tool_call(item: Any) -> ToolCall:
        try:
            parsed = json.loads(item.function.arguments or "{}")
            arguments = parsed if isinstance(parsed, dict) else {"raw_arguments": item.function.arguments}
            return ToolCall(call_id=item.id, name=item.function.name, arguments=arguments)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise LLMResponseNormalizationError("OpenAI returned an invalid tool call.") from error
