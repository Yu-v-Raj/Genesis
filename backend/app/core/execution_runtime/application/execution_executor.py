"""Deterministic placeholder executor for validating the execution pipeline."""

import asyncio

from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext


class ExecutionExecutor:
    """Run deterministic work without invoking AI, tools, memory, or workflows."""

    def __init__(self, delay_seconds: float = 2.0) -> None:
        if delay_seconds < 0:
            raise ValueError("Execution delay cannot be negative.")
        self._delay_seconds = delay_seconds

    async def execute(self, context: ExecutionContext) -> str:
        """Simulate deterministic work and return its fixed output."""
        await asyncio.sleep(self._delay_seconds)
        return "Execution completed successfully."
