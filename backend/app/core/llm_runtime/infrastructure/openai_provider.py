"""OpenAI SDK adapter; SDK specifics remain isolated here."""

import asyncio
import json
from typing import Any

from backend.app.core.core_services.config.settings import Settings
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.domain.exceptions import LLMConfigurationError, LLMProviderError, LLMResponseNormalizationError, LLMTimeoutError
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse, ToolCall, Usage


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.OPENAI_API_KEY.get_secret_value() if settings.OPENAI_API_KEY else None
        self._model = settings.OPENAI_MODEL
        self._timeout = settings.OPENAI_TIMEOUT_SECONDS

    @property
    def name(self) -> str:
        return "openai"

    def models(self) -> tuple[LLMModel, ...]:
        return (LLMModel(provider=self.name, model_name=self._model, capabilities=frozenset({"chat"}), metadata={"configured": True}),)

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
            completion = await client.chat.completions.create(model=request.model.model_name, messages=[{"role": message.role.value, "content": message.content} for message in request.messages], temperature=request.generation.temperature, max_tokens=request.generation.max_tokens)
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
    def _tool_call(item: Any) -> ToolCall:
        try:
            parsed = json.loads(item.function.arguments or "{}")
            arguments = parsed if isinstance(parsed, dict) else {"raw_arguments": item.function.arguments}
            return ToolCall(call_id=item.id, name=item.function.name, arguments=arguments)
        except (AttributeError, TypeError, json.JSONDecodeError) as error:
            raise LLMResponseNormalizationError("OpenAI returned an invalid tool call.") from error
