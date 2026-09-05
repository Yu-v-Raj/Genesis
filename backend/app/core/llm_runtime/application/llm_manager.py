"""Genesis-facing LLM generation orchestration."""

from time import monotonic

from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.llm_runtime.application.provider_registry import LLMProviderRegistry
from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse
from backend.app.core.observability.domain.events import LLMCompleted, LLMFailed, LLMRequested


class LLMManager:
    def __init__(self, registry: LLMProviderRegistry, event_bus: EventBus | None = None) -> None:
        self._registry = registry
        self._event_bus = event_bus

    def providers(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self._registry.providers())

    def models(self) -> tuple[LLMModel, ...]:
        return tuple(model for provider in self._registry.providers() for model in provider.models())

    async def generate(self, request: LLMRequest) -> LLMResponse:
        started = monotonic()
        try:
            provider = self._registry.resolve(request.model.provider)
        except Exception as error:
            await self._publish(LLMFailed, {"provider": request.model.provider, "model": request.model.model_name, "duration_ms": round((monotonic() - started) * 1000), "error_type": type(error).__name__})
            raise
        await self._publish(LLMRequested, {"provider": provider.name, "model": request.model.model_name})
        try:
            response = await provider.generate(request)
        except Exception as error:
            await self._publish(LLMFailed, {"provider": provider.name, "model": request.model.model_name, "duration_ms": round((monotonic() - started) * 1000), "error_type": type(error).__name__})
            raise
        await self._publish(LLMCompleted, {"provider": provider.name, "model": response.model.model_name, "duration_ms": round((monotonic() - started) * 1000), "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens, "total_tokens": response.usage.total_tokens}})
        return response

    async def _publish(self, event_type, payload: dict[str, object]) -> None:
        if self._event_bus is not None:
            await self._event_bus.publish(event_type(source="llm_manager", payload=payload))
