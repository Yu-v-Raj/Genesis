"""Lossless mapping between domain conversation messages and stored rows."""

import base64
from collections.abc import Mapping

from backend.app.core.llm_runtime.domain.models import Message, MessageRole, ToolCall


_COLUMN_KEYS = ("interaction_id", "tool_call_id", "tool_name", "tool_status")
_BYTES_MARKER = "$bytes"


def message_columns(message: Message) -> dict[str, object]:
    """Return the stored column values for one message.

    Message metadata carries only the keys the interaction service writes; anything else
    is runtime-only and intentionally not persisted.
    """
    if message.role is MessageRole.SYSTEM:
        raise ValueError("System instructions are assembled per turn and never stored.")
    metadata = message.metadata
    tool_calls = metadata.get("tool_calls")
    return {
        "role": message.role.value,
        "content": message.content,
        **{key: _optional_str(metadata.get(key)) for key in _COLUMN_KEYS},
        "tool_calls": None if not tool_calls else [_encode_tool_call(call) for call in tool_calls],
    }


def message_from_columns(
    *,
    role: str,
    content: str,
    interaction_id: str | None,
    tool_call_id: str | None,
    tool_name: str | None,
    tool_status: str | None,
    tool_calls: list[Mapping[str, object]] | None,
) -> Message:
    metadata: dict[str, object] = {
        key: value
        for key, value in (
            ("interaction_id", interaction_id),
            ("tool_call_id", tool_call_id),
            ("tool_name", tool_name),
            ("tool_status", tool_status),
        )
        if value is not None
    }
    if tool_calls:
        metadata["tool_calls"] = tuple(_decode_tool_call(call) for call in tool_calls)
    return Message(role=MessageRole(role), content=content, metadata=metadata)


def _encode_tool_call(call: object) -> dict[str, object]:
    if not isinstance(call, ToolCall):
        raise ValueError("Assistant tool-call metadata is invalid.")
    return {
        "call_id": call.call_id,
        "name": call.name,
        "arguments": dict(call.arguments),
        # Provider continuation data, e.g. Gemini thought signatures (bytes).
        "metadata": {key: _encode_value(value) for key, value in call.metadata.items()},
    }


def _decode_tool_call(data: Mapping[str, object]) -> ToolCall:
    metadata = data.get("metadata") or {}
    return ToolCall(
        call_id=str(data["call_id"]),
        name=str(data["name"]),
        arguments=dict(data.get("arguments") or {}),  # type: ignore[arg-type]
        metadata={key: _decode_value(value) for key, value in dict(metadata).items()},  # type: ignore[arg-type]
    )


def _encode_value(value: object) -> object:
    if isinstance(value, bytes):
        return {_BYTES_MARKER: base64.b64encode(value).decode("ascii")}
    return value


def _decode_value(value: object) -> object:
    if isinstance(value, Mapping) and set(value) == {_BYTES_MARKER}:
        return base64.b64decode(str(value[_BYTES_MARKER]))
    return value


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
