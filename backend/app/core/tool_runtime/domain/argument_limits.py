"""Finite size limits for tool arguments and caller-supplied metadata.

Checked by the tool policy before anything else touches the arguments (eligibility
lookups, approval requests, execution), when a workflow definition is saved, and on
metadata that callers attach to tool runs and executions. Oversized input is refused,
never truncated: an approval always covers exactly the arguments it was asked about.

The limits are deliberately generous. Every built-in tool and every payload the console
sends is far below them (the largest real arguments are well under 1 KiB), but they stop
a single request from filling memory, the event loop or the database.
"""

import json
from collections.abc import Mapping

MAX_ARGUMENT_BYTES = 64 * 1024  # serialized JSON, UTF-8
MAX_METADATA_BYTES = 16 * 1024
MAX_STRING_LENGTH = 16_384  # characters, for any string value
MAX_KEY_LENGTH = 256
MAX_ARRAY_ITEMS = 1_000
MAX_OBJECT_KEYS = 256
MAX_DEPTH = 16  # nested objects/arrays, the top-level object counting as 1

LIMITS_TEXT = (
    f"at most {MAX_ARGUMENT_BYTES // 1024} KiB in total, strings of up to {MAX_STRING_LENGTH:,} characters, "
    f"{MAX_ARRAY_ITEMS:,} items per list, {MAX_OBJECT_KEYS} fields per object and {MAX_DEPTH} levels of nesting"
)


def size_problem(value: object, *, max_bytes: int = MAX_ARGUMENT_BYTES, what: str = "The tool arguments") -> str | None:
    """Why ``value`` exceeds a limit (naming the limit, never the content), or None.

    Walks the structure iteratively and stops at the first breach, so an oversized payload
    costs no more than the limit to reject.
    """
    budget = max_bytes  # a running lower bound on the serialized size
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, Mapping):
            if depth > MAX_DEPTH:
                return f"{what} are nested more than {MAX_DEPTH} levels deep."
            if len(item) > MAX_OBJECT_KEYS:
                return f"{what} have an object with more than {MAX_OBJECT_KEYS} fields."
            for key, inner in item.items():
                if isinstance(key, str) and len(key) > MAX_KEY_LENGTH:
                    return f"{what} have a field name longer than {MAX_KEY_LENGTH} characters."
                budget -= len(str(key)) + 4
                pending.append((inner, depth + 1))
        elif isinstance(item, (list, tuple)):
            if depth > MAX_DEPTH:
                return f"{what} are nested more than {MAX_DEPTH} levels deep."
            if len(item) > MAX_ARRAY_ITEMS:
                return f"{what} have a list with more than {MAX_ARRAY_ITEMS:,} items."
            budget -= len(item) + 2
            pending.extend((inner, depth + 1) for inner in item)
        elif isinstance(item, str):
            if len(item) > MAX_STRING_LENGTH:
                return f"{what} have a text value longer than {MAX_STRING_LENGTH:,} characters."
            budget -= len(item) + 2
        else:
            budget -= 8
        if budget < 0:
            return f"{what} are larger than {max_bytes // 1024} KiB."
    try:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    except (TypeError, ValueError):
        return None  # not plain JSON; the schema check refuses it with its own message
    if len(encoded) > max_bytes:
        return f"{what} are larger than {max_bytes // 1024} KiB."
    return None
