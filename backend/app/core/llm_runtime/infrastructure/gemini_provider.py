"""Native Google Gemini SDK adapter for the provider-neutral LLM Runtime."""

import asyncio
import re
from collections.abc import Callable
from time import monotonic
from typing import Any

from backend.app.core.core_services.config.settings import Settings
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.domain.exceptions import (
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseNormalizationError,
    LLMTimeoutError,
)
from backend.app.core.llm_runtime.domain.models import (
    LLMModel,
    LLMRequest,
    LLMResponse,
    MessageRole,
    Usage,
)


class GeminiProvider(LLMProvider):
    """Google Gemini adapter that keeps ``google-genai`` types at the edge."""

    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: Callable[[str, float], Any] | None = None,
    ) -> None:
        self._api_key = (
            settings.GEMINI_API_KEY.get_secret_value()
            if settings.GEMINI_API_KEY
            else None
        )
        self._model = settings.GEMINI_MODEL
        self._timeout = settings.GEMINI_TIMEOUT_SECONDS
        self._client_factory = client_factory
        self._client: Any | None = None

    @property
    def name(self) -> str:
        return "gemini"

    def models(self) -> tuple[LLMModel, ...]:
        return (
            LLMModel(
                provider=self.name,
                model_name=self._model,
                capabilities=frozenset({"chat"}),
                metadata={"configured": self._api_key is not None},
            ),
        )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._api_key:
            raise LLMConfigurationError(
                "Gemini is not configured: GEMINI_API_KEY is required."
            )
        if request.model.provider != self.name:
            raise LLMProviderError("GeminiProvider received a request for another provider.")

        contents, config = self._request_payload(request)
        started = monotonic()
        try:
            response = await self._get_client().aio.models.generate_content(
                model=request.model.model_name,
                contents=contents,
                config=config,
            )
            return self._normalize_response(response, request.model)
        except asyncio.TimeoutError as error:
            self._log_generation_failure(error, request, started)
            raise LLMTimeoutError("Gemini generation timed out.") from error
        except (AttributeError, IndexError, TypeError, ValueError) as error:
            self._log_generation_failure(error, request, started)
            raise LLMResponseNormalizationError(
                "Gemini returned a response Genesis could not normalize."
            ) from error
        except (LLMConfigurationError, LLMProviderError) as error:
            self._log_generation_failure(error, request, started)
            raise
        except Exception as error:
            self._log_generation_failure(error, request, started)
            raise LLMProviderError("Gemini generation failed.") from error

    def _get_client(self) -> Any:
        if self._client is None:
            if self._client_factory is not None:
                self._client = self._client_factory(self._api_key, self._timeout)
            else:
                try:
                    from google import genai
                except ImportError as error:
                    raise LLMConfigurationError(
                        "Gemini support requires the optional 'google-genai' package."
                    ) from error
                self._client = genai.Client(
                    api_key=self._api_key,
                    http_options={"timeout": int(self._timeout * 1000)},
                )
        return self._client

    @staticmethod
    def _request_payload(request: LLMRequest) -> tuple[list[dict[str, object]], dict[str, object]]:
        contents: list[dict[str, object]] = []
        system_messages: list[str] = []
        for message in request.messages:
            if message.role is MessageRole.SYSTEM:
                system_messages.append(message.content)
                continue
            role = "model" if message.role is MessageRole.ASSISTANT else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        config: dict[str, object] = {}
        if request.generation.temperature is not None:
            config["temperature"] = request.generation.temperature
        if request.generation.max_tokens is not None:
            config["max_output_tokens"] = request.generation.max_tokens
        if system_messages:
            config["system_instruction"] = "\n\n".join(system_messages)
        return contents, config

    @classmethod
    def _normalize_response(cls, response: Any, model: LLMModel) -> LLMResponse:
        candidates = response.candidates or ()
        candidate = candidates[0] if candidates else None
        finish_reason = None if candidate is None else cls._finish_reason(candidate.finish_reason)
        usage_metadata = response.usage_metadata
        return LLMResponse(
            content=response.text,
            model=model,
            finish_reason=finish_reason,
            usage=Usage(
                input_tokens=cls._token_count(usage_metadata, "prompt_token_count"),
                output_tokens=cls._token_count(usage_metadata, "candidates_token_count"),
                total_tokens=cls._token_count(usage_metadata, "total_token_count"),
            ),
            tool_calls=(),
            metadata={},
        )

    @staticmethod
    def _finish_reason(value: Any) -> str | None:
        if value is None:
            return None
        normalized = getattr(value, "value", value)
        return str(normalized).lower()

    @staticmethod
    def _token_count(usage: Any, name: str) -> int | None:
        value = None if usage is None else getattr(usage, name, None)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def _log_generation_failure(
        self,
        error: Exception,
        request: LLMRequest,
        started: float,
    ) -> None:
        """Log provider diagnostics without credentials or request content."""
        logger.error(
            "Gemini generation failed",
            extra={
                "genesis_context": {
                    "exception_type": type(error).__name__,
                    "exception_message": self._sanitized_error_message(error, request),
                    "http_status_code": self._error_attribute(error, "code"),
                    "api_status": self._error_attribute(error, "status"),
                    "api_reason": self._error_attribute(error, "reason"),
                    "model": request.model.model_name,
                    "elapsed_ms": round((monotonic() - started) * 1000),
                }
            },
        )

    def _sanitized_error_message(self, error: Exception, request: LLMRequest) -> str:
        message = str(error)
        if self._api_key:
            message = message.replace(self._api_key, "[REDACTED]")
        for request_message in request.messages:
            message = message.replace(request_message.content, "[REDACTED]")
        message = re.sub(
            r"(?i)(authorization|x-goog-api-key|api[_-]?key)(\s*[:=]\s*)([^,\s]+)",
            r"\1\2[REDACTED]",
            message,
        )
        return message[:1000]

    @staticmethod
    def _error_attribute(error: Exception, name: str) -> str | int | float | None:
        value = getattr(error, name, None)
        return value if isinstance(value, (str, int, float)) else None
