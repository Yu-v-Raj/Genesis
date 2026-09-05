"""Provider boundary that keeps SDK types outside Genesis application code."""

from abc import ABC, abstractmethod

from backend.app.core.llm_runtime.domain.models import LLMModel, LLMRequest, LLMResponse


class LLMProvider(ABC):
    """A named, async, provider-neutral LLM generation adapter."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def models(self) -> tuple[LLMModel, ...]: ...

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
