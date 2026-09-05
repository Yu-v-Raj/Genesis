"""Provider-neutral immutable LLM Runtime records."""

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


def _mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(value))


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True, kw_only=True)
class Message:
    role: MessageRole
    content: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise ValueError("LLM message content must be a string.")
        object.__setattr__(self, "metadata", _mapping(self.metadata))


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMModel:
    provider: str
    model_name: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError("LLM model provider must be non-empty.")
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("LLM model name must be non-empty.")
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "metadata", _mapping(self.metadata))


@dataclass(frozen=True, slots=True, kw_only=True)
class GenerationConfig:
    temperature: float | None = None
    max_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("LLM temperature must be between 0 and 2.")
        if self.max_tokens is not None and self.max_tokens < 1:
            raise ValueError("LLM max_tokens must be positive.")


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMRequest:
    model: LLMModel
    messages: tuple[Message, ...]
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("LLM requests require at least one message.")
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "metadata", _mapping(self.metadata))


@dataclass(frozen=True, slots=True, kw_only=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        if any(value is not None and value < 0 for value in (self.input_tokens, self.output_tokens, self.total_tokens)):
            raise ValueError("LLM token usage cannot be negative.")


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCall:
    call_id: str
    name: str
    arguments: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.call_id or not self.name:
            raise ValueError("LLM tool calls require an ID and name.")
        object.__setattr__(self, "arguments", _mapping(self.arguments))


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMResponse:
    content: str | None
    model: LLMModel
    finish_reason: str | None = None
    usage: Usage = field(default_factory=Usage)
    tool_calls: tuple[ToolCall, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.content is not None and not isinstance(self.content, str):
            raise ValueError("LLM response content must be a string or None.")
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "metadata", _mapping(self.metadata))
