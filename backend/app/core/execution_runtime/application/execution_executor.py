"""Deterministic placeholder executor for validating the execution pipeline."""

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING

from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext

if TYPE_CHECKING:
    from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager


class ExecutionExecutor:
    """Run deterministic work without invoking AI, tools, memory, or workflows."""

    def __init__(self, delay_seconds: float = 2.0) -> None:
        if delay_seconds < 0:
            raise ValueError("Execution delay cannot be negative.")
        self._delay_seconds = delay_seconds
        self._tool_manager: ToolRuntimeManager | None = None

    def set_tool_manager(self, tool_manager: "ToolRuntimeManager") -> None:
        """Attach the optional Tool Runtime submission boundary during bootstrap."""
        self._tool_manager = tool_manager

    def may_have_side_effects(self, metadata: Mapping[str, object]) -> bool:
        """Whether re-running this work could repeat an external effect.

        The deterministic placeholder has none. Tool work defers to the tool's declared
        ``side_effects``; an unknown or unregistered tool is assumed to have them.
        """
        tool_name = metadata.get("tool_name")
        if not isinstance(tool_name, str):
            return False
        if self._tool_manager is None:
            return True
        try:
            return self._tool_manager.get_tool(tool_name).definition.side_effects
        except Exception:
            return True

    async def execute(self, context: ExecutionContext) -> str:
        """Simulate deterministic work and return its fixed output."""
        tool_name = context.metadata.get("tool_name")
        if isinstance(tool_name, str) and self._tool_manager is not None:
            arguments = context.metadata.get("tool_arguments")
            task = await self._tool_manager.execute(
                tool_name=tool_name,
                arguments=arguments if isinstance(arguments, dict) else {},
                execution_id=context.execution_id,
            )
            if task.result is None or task.result.error is not None:
                raise RuntimeError(task.result.error if task.result is not None else "Tool task failed.")
            return str(task.result.output)
        await asyncio.sleep(self._delay_seconds)
        return "Execution completed successfully."
