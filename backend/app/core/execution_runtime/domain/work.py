"""Contracts between the execution worker and the handlers that perform specific kinds of work."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from backend.app.core.execution_runtime.domain.execution import Execution
from backend.app.core.execution_runtime.domain.execution_context import ExecutionContext


@dataclass(frozen=True, slots=True)
class WorkOutcome:
    """What a handler produced: the stored text ``output`` and an in-process ``value``.

    ``value`` is handed to a caller waiting on this execution in the same process (for
    example the HTTP chat request) and is never persisted.
    """

    output: str
    value: object = None


@dataclass(frozen=True, slots=True)
class RecoveryVerdict:
    """A handler's finding about work whose worker stopped while it was RUNNING."""

    completed: bool
    output: str | None = None
    detail: str = ""


class WorkHandler(Protocol):
    """Performs one kind of execution (selected by ``metadata["kind"]``)."""

    async def run(self, context: ExecutionContext) -> WorkOutcome: ...

    def may_have_side_effects(self, metadata: Mapping[str, object], checkpoint: Mapping[str, object]) -> bool:
        """Whether repeating this work could repeat an external effect, given its checkpoint."""
        ...

    def error_category(self, error: BaseException) -> str: ...

    async def reconcile(self, execution: Execution) -> RecoveryVerdict:
        """Inspect persisted evidence to decide if interrupted work had actually finished."""
        ...
