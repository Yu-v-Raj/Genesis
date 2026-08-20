"""Tool contract and deterministic built-in Tool factories."""

import ast
import asyncio
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


def _calculate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        left, right = _calculate(node.left), _calculate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise ToolValidationError("Exponent is outside the supported range.")
        return _OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_calculate(node.operand))
    raise ToolValidationError("Expression contains unsupported arithmetic.")


async def _calculator(request: ToolRequest) -> ToolResult:
    expression = _required_string(request.arguments, "expression")
    try:
        parsed = ast.parse(expression, mode="eval")
        output = _calculate(parsed.body)
    except (SyntaxError, ZeroDivisionError) as error:
        raise ToolValidationError("Expression is not valid safe arithmetic.") from error
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
        Tool(definition=ToolMetadata(name="echo", description="Return a supplied message.", capabilities=(ToolCapability.ECHO,), permissions=permission), handler=_echo),
        Tool(definition=ToolMetadata(name="calculator", description="Evaluate safe arithmetic.", capabilities=(ToolCapability.CALCULATION,), permissions=permission), handler=_calculator),
        Tool(definition=ToolMetadata(name="uuid", description="Generate a random UUID.", capabilities=(ToolCapability.IDENTIFIER_GENERATION,), permissions=permission), handler=_uuid),
        Tool(definition=ToolMetadata(name="random_number", description="Generate an integer in an inclusive range.", capabilities=(ToolCapability.RANDOM_NUMBER,), permissions=permission), handler=_random_number),
        Tool(definition=ToolMetadata(name="delay", description="Wait for a bounded duration.", capabilities=(ToolCapability.DELAY,), permissions=permission), handler=_delay),
    )
