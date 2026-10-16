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


class WorkSuspended(Exception):
    """Raised by a handler to pause durably until an external decision exists.

    The worker stores ``checkpoint`` (everything needed to resume, merged into the
    execution's checkpoint), moves the execution to WAITING_APPROVAL without a lease, and
    re-queues it once the ``ResumeGate`` reports ``token`` resolved. The handler then runs
    again with that checkpoint in its context.
    """

    def __init__(self, token: str, checkpoint: Mapping[str, object], message: str) -> None:
        super().__init__(message)
        self.token = token
        self.checkpoint = dict(checkpoint)
        self.message = message


@dataclass(frozen=True, slots=True)
class SuspendedOutcome:
    """Handed to an in-process waiter (e.g. the HTTP chat request) when work suspends."""

    token: str
    message: str


class ResumeGate(Protocol):
    """Answers whether the decision a suspended execution waits on exists yet."""

    async def is_resolved(self, token: str) -> bool: ...

    async def abandon(self, token: str, reason: str) -> None:
        """The waiting work was cancelled; the decision it waited on is no longer needed."""
        ...


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
