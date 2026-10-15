"""The calculator refuses expensive input before computing it (H1).

Tools run on the server's event loop, so a slow calculation would stall every request.
Spies on the arithmetic operators prove that rejected input never reaches the expensive
operation; nothing here performs a large calculation.
"""

import ast
from time import perf_counter

import pytest

from backend.app.core.tool_runtime.domain import tool as calculator
from backend.app.core.tool_runtime.domain.exceptions import ToolValidationError
from backend.app.core.tool_runtime.domain.tool import (
    MAX_EXPRESSION_DEPTH,
    MAX_EXPRESSION_LENGTH,
    MAX_EXPRESSION_NODES,
    MAX_INTEGER_BITS,
    evaluate_expression,
)


@pytest.fixture
def operator_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, object, object]]:
    """Record every arithmetic operation the calculator actually performs."""
    calls: list[tuple[str, object, object]] = []
    for op, function in list(calculator._OPERATORS.items()):
        def spy(left, right, _name=op.__name__, _function=function):
            calls.append((_name, left, right))
            return _function(left, right)
        monkeypatch.setitem(calculator._OPERATORS, op, spy)
    return calls


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("2 + 5 * 10", 52), ("7 / 2", 3.5), ("2 ** 10", 1024), ("-3 ** 2", -9), ("2 ** -2", 0.25), ("10 % 3", 1),
     ("9 ** 99 % 7", pow(9, 99, 7)), ("(((((1 + 2)))))", 3), ("1.5 * 4", 6.0), ("2 ** 100", 2**100)],
)
def test_normal_arithmetic_is_unchanged(expression: str, expected: object) -> None:
    assert evaluate_expression(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "(9**99)**99",
        "(((9**99)**99)**99)**99",  # minutes of CPU and gigabytes before this fix
        "(2**99)**41",
    ],
)
def test_oversized_powers_are_refused_before_they_are_computed(expression: str, operator_calls: list) -> None:
    started = perf_counter()
    with pytest.raises(ToolValidationError, match="too large"):
        evaluate_expression(expression)

    assert perf_counter() - started < 0.5
    big_operands = [call for call in operator_calls if isinstance(call[1], int) and call[1].bit_length() > 200]
    assert big_operands == []  # only the cheap inner 9**99 / 2**99 ever ran


def test_oversized_products_are_refused_before_they_are_computed(operator_calls: list) -> None:
    # 14 factors of 9**99 (314 bits each): within the shape limits, over the size limit.
    with pytest.raises(ToolValidationError, match="too large"):
        evaluate_expression("*".join(["9**99"] * 14))

    products = [call for call in operator_calls if call[0] == "Mult"]
    assert products and all(left.bit_length() + right.bit_length() <= MAX_INTEGER_BITS for _, left, right in products)


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("1" + " + 1" * MAX_EXPRESSION_LENGTH, "longer than"),
        ("+".join(["1"] * (MAX_EXPRESSION_NODES // 2 + 1)), "too complex"),
        ("-" * (MAX_EXPRESSION_DEPTH + 1) + "1", "too complex"),
        ("__import__('os')", "unsupported"),
        ("(1).real", "unsupported"),
        ("True + 1", "unsupported"),
    ],
)
def test_shape_limits_reject_before_any_arithmetic(expression: str, message: str, operator_calls: list) -> None:
    with pytest.raises(ToolValidationError, match=message):
        evaluate_expression(expression)
    assert operator_calls == []


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("1e308 * 10", "too large"),  # float overflow to infinity
        ("1e309", "too large"),  # an infinite literal
        ("(-8) ** 0.5", "not a real number"),  # complex result
        ("2 ** 101", "Exponent is outside"),
        ("1 / 0", "not valid"),
        ("((2**100)**40) / 3**-90", "too large"),  # a 4,000-bit int is too large for a float
    ],
)
def test_results_must_be_finite_real_numbers(expression: str, message: str) -> None:
    with pytest.raises(ToolValidationError, match=message):
        evaluate_expression(expression)


def test_the_largest_allowed_integer_is_still_cheap() -> None:
    started = perf_counter()
    value = evaluate_expression("2 ** 100 * 2 ** 100 * 2 ** 100 * 2 ** 100")

    assert value == 2**400 and perf_counter() - started < 0.1


def test_parentheses_do_not_count_toward_complexity() -> None:
    assert isinstance(ast.parse("((((((((((((((((((((1))))))))))))))))))))", mode="eval").body, ast.Constant)
    assert evaluate_expression("((((((((((((((((((((1))))))))))))))))))))") == 1
