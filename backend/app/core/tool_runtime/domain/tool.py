"""Tool contract and deterministic built-in Tool factories."""

import ast
import asyncio
import math
import operator
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from time import monotonic
from uuid import uuid4

from backend.app.core.tool_runtime.domain.exceptions import ToolValidationError
from backend.app.core.tool_runtime.domain.tool_metadata import ToolMetadata
from backend.app.core.tool_runtime.domain.tool_capability import ToolCapability
from backend.app.core.tool_runtime.domain.tool_permission import ToolPermission
from backend.app.core.tool_runtime.domain.tool_request import ToolRequest
from backend.app.core.tool_runtime.domain.tool_result import ToolResult
from backend.app.core.tool_runtime.domain.tool_status import ToolResultStatus


ToolHandler = Callable[[ToolRequest], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True, kw_only=True)
class Tool:
    """A declarative, immutable tool definition with an asynchronous implementation."""

    definition: ToolMetadata
    handler: ToolHandler

    @property
    def name(self) -> str:
        return self.definition.name

    async def execute(self, request: ToolRequest) -> ToolResult:
        """Execute the implementation against an already validated request."""
        return await self.handler(request)


def _required_string(arguments: Mapping[str, object], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ToolValidationError(f"Argument '{name}' must be a string.")
    return value


def _required_int(arguments: Mapping[str, object], name: str) -> int:
    value = arguments.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ToolValidationError(f"Argument '{name}' must be an integer.")
    return value


async def _echo(request: ToolRequest) -> ToolResult:
    output = _required_string(request.arguments, "message")
    return ToolResult(status=ToolResultStatus.COMPLETED, output=output)


_OPERATORS: dict[type[ast.operator], Callable[[int | float, int | float], int | float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[int | float], int | float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


# Limits that keep every calculation cheap. Tools run on the server's event loop, so an
# expensive expression must be refused before it is computed, not interrupted afterwards.
MAX_EXPRESSION_LENGTH = 200
MAX_EXPRESSION_NODES = 64
MAX_EXPRESSION_DEPTH = 16
MAX_EXPONENT = 100
MAX_INTEGER_BITS = 4096  # about 1,230 decimal digits


def _check_shape(root: ast.AST) -> None:
    """Reject oversized or unsupported expressions before any arithmetic runs."""
    nodes = 0
    pending: list[tuple[ast.AST, int]] = [(root, 1)]
    while pending:
        node, depth = pending.pop()
        nodes += 1
        if nodes > MAX_EXPRESSION_NODES or depth > MAX_EXPRESSION_DEPTH:
            raise ToolValidationError("Expression is too complex.")
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise ToolValidationError("Expression contains unsupported arithmetic.")
        elif isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            pending += [(node.left, depth + 1), (node.right, depth + 1)]
        elif isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            pending.append((node.operand, depth + 1))
        else:
            raise ToolValidationError("Expression contains unsupported arithmetic.")


def _check_cost(op: ast.operator, left: int | float, right: int | float) -> None:
    """Refuse an operation whose result would be too large, before computing it."""
    if isinstance(op, ast.Pow):
        if abs(right) > MAX_EXPONENT:
            raise ToolValidationError("Exponent is outside the supported range.")
        if isinstance(left, int) and isinstance(right, int) and right > 0 and max(left.bit_length(), 1) * right > MAX_INTEGER_BITS:
            raise ToolValidationError("Result is too large.")
    elif isinstance(op, ast.Mult) and isinstance(left, int) and isinstance(right, int):
        if left.bit_length() + right.bit_length() > MAX_INTEGER_BITS:
            raise ToolValidationError("Result is too large.")


def _bounded(value: object) -> int | float:
    """Every intermediate result must be a finite real number of bounded size."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolValidationError("Result is not a real number.")
    if isinstance(value, int) and value.bit_length() > MAX_INTEGER_BITS:
        raise ToolValidationError("Result is too large.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ToolValidationError("Result is too large.")
    return value


def _calculate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return _bounded(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _calculate(node.left), _calculate(node.right)
        _check_cost(node.op, left, right)
        return _bounded(_OPERATORS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _bounded(_UNARY_OPERATORS[type(node.op)](_calculate(node.operand)))
    raise ToolValidationError("Expression contains unsupported arithmetic.")


def evaluate_expression(expression: str) -> int | float:
    """Safely evaluate bounded arithmetic, or raise ToolValidationError."""
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ToolValidationError(f"Expression is longer than {MAX_EXPRESSION_LENGTH} characters.")
    try:
        parsed = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError, MemoryError) as error:
        raise ToolValidationError("Expression is not valid safe arithmetic.") from error
    _check_shape(parsed.body)
    try:
        return _calculate(parsed.body)
    except ZeroDivisionError as error:
        raise ToolValidationError("Expression is not valid safe arithmetic.") from error
    except OverflowError as error:  # e.g. an int too large to convert to float
        raise ToolValidationError("Result is too large.") from error


async def _calculator(request: ToolRequest) -> ToolResult:
    output = evaluate_expression(_required_string(request.arguments, "expression"))
    return ToolResult(status=ToolResultStatus.COMPLETED, output=output)


async def _uuid(_: ToolRequest) -> ToolResult:
    return ToolResult(status=ToolResultStatus.COMPLETED, output=str(uuid4()))


async def _random_number(request: ToolRequest) -> ToolResult:
    minimum, maximum = _required_int(request.arguments, "min"), _required_int(request.arguments, "max")
    if minimum > maximum:
        raise ToolValidationError("Argument 'min' cannot exceed 'max'.")
    return ToolResult(status=ToolResultStatus.COMPLETED, output=random.randint(minimum, maximum))


async def _delay(request: ToolRequest) -> ToolResult:
    seconds = request.arguments.get("seconds")
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds < 0 or seconds > 60:
        raise ToolValidationError("Argument 'seconds' must be a number between 0 and 60.")
    started = monotonic()
    await asyncio.sleep(seconds)
    return ToolResult(
        status=ToolResultStatus.COMPLETED,
        output="Completed after waiting.",
        duration=monotonic() - started,
    )


def builtin_tools() -> tuple[Tool, ...]:
    """Return the deterministic built-in Tool definitions registered at startup."""
    permission = (ToolPermission.NONE,)
    return (
        Tool(
            definition=ToolMetadata(
                name="echo",
                description="Return a supplied message.",
                capabilities=(ToolCapability.ECHO,),
                permissions=permission,
                side_effects=False,
                parameters={
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                },
            ),
            handler=_echo,
        ),
        Tool(
            definition=ToolMetadata(
                name="calculator",
                description="Evaluate safe arithmetic.",
                capabilities=(ToolCapability.CALCULATION,),
                permissions=permission,
                side_effects=False,
                parameters={
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            ),
            handler=_calculator,
        ),
        Tool(
            definition=ToolMetadata(
                name="uuid",
                description="Generate a random UUID.",
                capabilities=(ToolCapability.IDENTIFIER_GENERATION,),
                permissions=permission,
                side_effects=False,
            ),
            handler=_uuid,
        ),
        Tool(
            definition=ToolMetadata(
                name="random_number",
                description="Generate an integer in an inclusive range.",
                capabilities=(ToolCapability.RANDOM_NUMBER,),
                permissions=permission,
                side_effects=False,
                parameters={
                    "type": "object",
                    "properties": {"min": {"type": "integer"}, "max": {"type": "integer"}},
                    "required": ["min", "max"],
                },
            ),
            handler=_random_number,
        ),
        Tool(
            definition=ToolMetadata(
                name="delay",
                description="Wait for a bounded duration.",
                capabilities=(ToolCapability.DELAY,),
                permissions=permission,
                side_effects=False,
                parameters={
                    "type": "object",
                    "properties": {"seconds": {"type": "number", "minimum": 0, "maximum": 60}},
                    "required": ["seconds"],
                },
            ),
            handler=_delay,
        ),
    )
