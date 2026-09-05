"""Stable LLM Runtime failure categories."""


class LLMRuntimeError(Exception):
    """Base class for provider-agnostic LLM Runtime failures."""


class ProviderNotFoundError(LLMRuntimeError):
    pass


class ProviderUnavailableError(LLMRuntimeError):
    pass


class LLMConfigurationError(ProviderUnavailableError):
    pass


class LLMProviderError(LLMRuntimeError):
    pass


class LLMTimeoutError(LLMProviderError):
    pass


class LLMResponseNormalizationError(LLMProviderError):
    pass
