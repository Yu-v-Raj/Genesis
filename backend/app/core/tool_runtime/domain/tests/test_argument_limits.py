"""Tool arguments and caller metadata have finite, generous size limits."""

import pytest

from backend.app.core.tool_runtime.domain.argument_limits import (
    MAX_ARGUMENT_BYTES,
    MAX_ARRAY_ITEMS,
    MAX_DEPTH,
    MAX_KEY_LENGTH,
    MAX_METADATA_BYTES,
    MAX_OBJECT_KEYS,
    MAX_STRING_LENGTH,
    size_problem,
)
from backend.app.core.tool_runtime.domain.tool import builtin_tools


def nested(depth: int) -> dict:
    value: dict = {"leaf": 1}
    for _ in range(depth - 1):
        value = {"x": value}
    return value


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "Hello Genesis"},
        {"expression": "2 + 5 * 10"},
        {},
        {"min": 1, "max": 100},
        {"seconds": 2},
        {"note": "Try the approval flow"},
        {"text": "x" * MAX_STRING_LENGTH},  # exactly at the limit
        {"items": list(range(MAX_ARRAY_ITEMS))},
        {f"k{i}": i for i in range(MAX_OBJECT_KEYS)},
        nested(MAX_DEPTH),
    ],
)
def test_real_and_boundary_payloads_are_accepted(payload: dict) -> None:
    assert size_problem(payload) is None


@pytest.mark.parametrize(
    ("payload", "limit"),
    [
        ({"text": "x" * (MAX_STRING_LENGTH + 1)}, "longer than 16,384 characters"),
        ({"items": list(range(MAX_ARRAY_ITEMS + 1))}, "more than 1,000 items"),
        ({f"k{i}": i for i in range(MAX_OBJECT_KEYS + 1)}, "more than 256 fields"),
        ({"k" * (MAX_KEY_LENGTH + 1): 1}, "field name longer than 256"),
        (nested(MAX_DEPTH + 1), "nested more than 16 levels"),
        ({"chunks": ["y" * 10_000] * 7}, "larger than 64 KiB"),
    ],
)
def test_each_limit_is_named_without_echoing_the_content(payload: dict, limit: str) -> None:
    problem = size_problem(payload)
    assert problem is not None and limit in problem
    assert "xxxx" not in problem and "yyyy" not in problem


def test_metadata_has_its_own_smaller_budget() -> None:
    payload = {"note": "z" * (MAX_METADATA_BYTES)}
    assert size_problem(payload) is None
    assert "larger than 16 KiB" in (size_problem(payload, max_bytes=MAX_METADATA_BYTES, what="The run's metadata") or "")
    assert MAX_METADATA_BYTES < MAX_ARGUMENT_BYTES


def test_every_builtin_tool_is_far_below_the_limits() -> None:
    for tool in builtin_tools():
        assert size_problem(dict(tool.definition.parameters)) is None
