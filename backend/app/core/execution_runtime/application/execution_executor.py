"""Performs the work of an execution: registered handlers by kind, a tool call, or a placeholder."""

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING

from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext
from backend.app.core.execution_runtime.domain.work import RecoveryVerdict, WorkHandler, WorkOutcome
from backend.app.core.tool_runtime.domain.authorization import AgentToolContext, ToolAuthorizationError

if TYPE_CHECKING:
    from backend.app.core.tool_runtime.application.tool_manager import ToolRuntimeManager


class ExecutionExecutor:
    """Route each execution to the code that performs it.

    ``metadata["kind"]`` selects a registered ``WorkHandler`` (for example ``"chat"``).
    Without a kind, ``metadata["tool_name"]`` runs one tool through Tool Runtime on behalf
    of the execution's Agent, so the Agent's allowed tools and the full tool policy apply.
    Anything else runs the deterministic placeholder.
    """

    def __init__(self, delay_seconds: float = 2.0) -> None:
        if delay_seconds < 0:
            raise ValueError("Execution delay cannot be negative.")
        self._delay_seconds = delay_seconds
        self._tool_manager: ToolRuntimeManager | None = None
        self._handlers: dict[str, WorkHandler] = {}

    def set_tool_manager(self, tool_manager: "ToolRuntimeManager") -> None:
        """Attach the optional Tool Runtime submission boundary during bootstrap."""
        self._tool_manager = tool_manager

    def register_handler(self, kind: str, handler: WorkHandler) -> None:
        if kind in self._handlers:
            raise ValueError(f"A handler for '{kind}' work is already registered.")
        self._handlers[kind] = handler

    def handles(self, kind: str) -> bool:
        return kind in self._handlers

    def may_have_side_effects(
        self, metadata: Mapping[str, object], checkpoint: Mapping[str, object] | None = None
    ) -> bool:
        """Whether re-running this work could repeat an external effect.

        Handlers decide from their checkpoint. Tool work defers to the tool's declared
        ``side_effects``; an unknown or unregistered tool is assumed to have them. The
        deterministic placeholder has none.
        """
        handler = self._handler(metadata)
        if handler is not None:
            return handler.may_have_side_effects(metadata, checkpoint or {})
        if isinstance(metadata.get("kind"), str):
            return True  # unknown kind of work: assume it could have effects
        tool_name = metadata.get("tool_name")
        if not isinstance(tool_name, str):
            return False
        if self._tool_manager is None:
            return True
        try:
            return self._tool_manager.get_tool(tool_name).definition.side_effects
        except Exception:
            return True

    def error_category(self, metadata: Mapping[str, object], error: BaseException) -> str:
        handler = self._handler(metadata)
        if handler is not None:
            return handler.error_category(error)
        if isinstance(error, ToolAuthorizationError):
            return "tool_denied"
        return "tool_failed" if "tool_name" in metadata else "execution_failed"

    async def reconcile(self, execution: Execution) -> RecoveryVerdict:
        """Ask the handler whether interrupted work had in fact finished; others never did."""
        handler = self._handler(execution.metadata)
        if handler is None:
            return RecoveryVerdict(completed=False)
        return await handler.reconcile(execution)

    async def execute(self, context: ExecutionContext) -> str | WorkOutcome:
        handler = self._handler(context.metadata)
        if handler is not None:
            return await handler.run(context)
        if isinstance(context.metadata.get("kind"), str):
            raise RuntimeError(f"No handler is registered for '{context.metadata['kind']}' work.")
        tool_name = context.metadata.get("tool_name")
        if isinstance(tool_name, str) and self._tool_manager is not None:
            arguments = context.metadata.get("tool_arguments")
            task = await self._tool_manager.execute(
                tool_name=tool_name,
                arguments=arguments if isinstance(arguments, dict) else {},
                context=AgentToolContext(agent_id=context.agent_id, execution_id=context.execution_id),
            )
            if task.result is None or task.result.error is not None:
                raise RuntimeError(task.result.error if task.result is not None else "Tool task failed.")
            return str(task.result.output)
        await asyncio.sleep(self._delay_seconds)
        return "Execution completed successfully."

    def _handler(self, metadata: Mapping[str, object]) -> WorkHandler | None:
        kind = metadata.get("kind")
        return self._handlers.get(kind) if isinstance(kind, str) else None
