"""Thread-safe registry of LLM provider adapters."""

from threading import RLock

from backend.app.core.llm_runtime.application.provider import LLMProvider
from backend.app.core.llm_runtime.domain.exceptions import ProviderNotFoundError


class LLMProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._lock = RLock()

    def register(self, provider: LLMProvider) -> None:
        if not isinstance(provider, LLMProvider):
            raise TypeError("LLM providers must implement LLMProvider.")
        name = provider.name.strip()
        if not name:
            raise ValueError("LLM provider names must be non-empty.")
        with self._lock:
            if name in self._providers:
                raise ValueError(f"An LLM provider named {name!r} is already registered.")
            self._providers[name] = provider

    def resolve(self, name: str) -> LLMProvider:
        with self._lock:
            try:
                return self._providers[name]
            except KeyError as error:
                raise ProviderNotFoundError(f"No LLM provider named {name!r} is registered.") from error

    def providers(self) -> tuple[LLMProvider, ...]:
        with self._lock:
            return tuple(self._providers.values())
