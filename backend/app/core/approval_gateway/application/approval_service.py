"""The Approval Gateway: durable requests, operator decisions, and single-use consumption.

This service is the only thing that changes approval state. The tool policy asks it to
``resolve`` an operation (find or open the request standing for it) and the Tool Runtime
``consume``s an approval immediately before running the tool. Decisions come from the
operator through the API. Runtimes that wait on a request (chat turns, workflow steps)
learn about decisions through listeners and by asking ``state_of`` on their own ticks, so
a decision made while the process was down is still acted on after a restart.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from uuid import UUID

from backend.app.core.approval_gateway.application.repositories import ApprovalRepository
from backend.app.core.approval_gateway.domain.approval import (
    ACTIVE_STATES,
    Approval,
    ApprovalNotFoundError,
    ApprovalOutcome,
    ApprovalResolution,
    ApprovalState,
    ApprovalTransitionError,
    DecisionSource,
    OperationBinding,
    utc_now,
)
from backend.app.core.core_services.event_bus import EventBus
from backend.app.core.core_services.logging.logger import logger
from backend.app.core.core_services.persistence import PersistenceConflictError
from backend.app.core.observability.domain.events import ApprovalEvent

DEFAULT_TTL_SECONDS = 3600.0

ApprovalListener = Callable[[Approval], Awaitable[None] | None]

_EVENT_FOR_STATE = {
    ApprovalState.APPROVED: "approval.approved",
    ApprovalState.REJECTED: "approval.rejected",
    ApprovalState.EXPIRED: "approval.expired",
    ApprovalState.CANCELLED: "approval.cancelled",
    ApprovalState.CONSUMED: "approval.consumed",
}


class ApprovalService:
    def __init__(
        self,
        repository: ApprovalRepository,
        event_bus: EventBus,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("Approval lifetime must be positive.")
        self._repository = repository
        self._events = event_bus
        self._ttl = timedelta(seconds=ttl_seconds)
        self._clock = clock
        self._listeners: list[ApprovalListener] = []

    def add_listener(self, listener: ApprovalListener) -> None:
        """Called after a request is decided, expires or is cancelled (best effort; waiters
        also poll, so a missed notification only delays them)."""
        self._listeners.append(listener)

    # ------------------------------------------------------ used by the tool policy

    async def resolve(self, binding: OperationBinding, *, reason: str) -> ApprovalResolution:
        active = await self._repository.active_for(binding.digest)
        if active is not None:
            active = await self._expire_if_due(active)
            if active.state in ACTIVE_STATES:
                return _resolution(active)
        created = Approval(binding=binding, reason=reason, expires_at=self._clock() + self._ttl)
        stored = await self._repository.add_or_get_active(created)
        if stored.approval_id == created.approval_id:
            await self._publish("approval.requested", stored)
        return _resolution(stored)

    async def consume(self, approval_id: UUID, operation_digest: str) -> bool:
        current = await self._repository.get(approval_id)
        if current is None or current.operation_digest != operation_digest:
            return False
        current = await self._expire_if_due(current)
        if current.state is not ApprovalState.APPROVED:
            return False
        try:
            consumed = await self._repository.save(current, current.transition(ApprovalState.CONSUMED, consumed_at=self._clock()))
        except PersistenceConflictError:
            return False  # someone else consumed, cancelled or expired it first
        await self._publish("approval.consumed", consumed)
        return True

    async def record_outcome(self, approval_id: UUID, *, task_id: UUID | None, outcome: ApprovalOutcome, detail: str | None = None) -> None:
        for _ in range(3):
            current = await self._repository.get(approval_id)
            if current is None or current.state is not ApprovalState.CONSUMED or current.outcome is not None:
                return
            try:
                saved = await self._repository.save(current, current.transition_outcome(task_id=task_id, outcome=outcome, detail=detail))
            except PersistenceConflictError:
                continue
            await self._publish("approval.outcome", saved)
            return

    async def state_of(self, approval_id: UUID) -> ApprovalState | None:
        current = await self._repository.get(approval_id)
        return None if current is None else (await self._expire_if_due(current)).state

    # --------------------------------------------------------------- decisions

    async def approve(self, approval_id: UUID, *, source: DecisionSource) -> Approval:
        return await self._decide(approval_id, ApprovalState.APPROVED, source=source)

    async def reject(self, approval_id: UUID, *, source: DecisionSource) -> Approval:
        return await self._decide(approval_id, ApprovalState.REJECTED, source=source, detail="Rejected by the operator.")

    async def cancel(self, approval_id: UUID, *, reason: str, source: DecisionSource = DecisionSource.SYSTEM) -> Approval | None:
        """Cancel an active request; returns None if it is unknown or already final."""
        for _ in range(3):
            current = await self._repository.get(approval_id)
            if current is None or current.state not in ACTIVE_STATES:
                return current
            try:
                saved = await self._repository.save(
                    current,
                    current.transition(ApprovalState.CANCELLED, decided_at=self._clock(), decision_source=source, detail=reason),
                )
            except PersistenceConflictError:
                continue
            await self._changed(saved)
            return saved
        return await self._repository.get(approval_id)

    async def _decide(self, approval_id: UUID, target: ApprovalState, *, source: DecisionSource, detail: str | None = None) -> Approval:
        current = await self.get(approval_id)  # applies expiry first
        if current.state is not ApprovalState.PENDING:
            raise ApprovalTransitionError(current.state, target)
        try:
            saved = await self._repository.save(
                current, current.transition(target, decided_at=self._clock(), decision_source=source, detail=detail)
            )
        except PersistenceConflictError:
            # A concurrent decision won; report what it decided instead of overwriting it.
            latest = await self.get(approval_id)
            raise ApprovalTransitionError(latest.state, target) from None
        await self._changed(saved)
        return saved

    # ------------------------------------------------------------------- reading

    async def get(self, approval_id: UUID) -> Approval:
        current = await self._repository.get(approval_id)
        if current is None:
            raise ApprovalNotFoundError(approval_id)
        return await self._expire_if_due(current)

    async def list(self, *, states: frozenset[ApprovalState] | None = None, limit: int = 100) -> tuple[Approval, ...]:
        await self.expire_due()
        return await self._repository.list(states, limit)

    async def related(self, *, execution_id: UUID | None = None, workflow_id: UUID | None = None, limit: int = 200) -> tuple[Approval, ...]:
        """Requests of one execution or workflow run, as stored: reading never changes them
        (a pending request past its deadline is shown with its ``expires_at``)."""
        return await self._repository.related(execution_id=execution_id, workflow_id=workflow_id, limit=limit)

    async def expire_due(self) -> int:
        expired = 0
        for item in await self._repository.due_for_expiry(self._clock()):
            if (await self._expire_if_due(item)).state is ApprovalState.EXPIRED:
                expired += 1
        return expired

    async def _expire_if_due(self, current: Approval) -> Approval:
        if not current.is_expired(self._clock()):
            return current
        try:
            saved = await self._repository.save(
                current,
                current.transition(
                    ApprovalState.EXPIRED,
                    decided_at=self._clock(),
                    decision_source=DecisionSource.SYSTEM,
                    detail="No decision was recorded before the request expired."
                    if current.state is ApprovalState.PENDING
                    else "The approved operation did not run before the approval expired.",
                ),
            )
        except PersistenceConflictError:
            latest = await self._repository.get(current.approval_id)
            return current if latest is None else latest
        await self._changed(saved)
        return saved

    # -------------------------------------------------------------- notifications

    async def _changed(self, approval: Approval) -> None:
        await self._publish(_EVENT_FOR_STATE[approval.state], approval)
        for listener in list(self._listeners):
            try:
                result = listener(approval)
                if result is not None:
                    await result
            except Exception as error:  # a listener must never undo a stored decision
                logger.error("Approval listener failed", extra={"genesis_context": {"error_type": type(error).__name__}})

    async def _publish(self, event_type: str, approval: Approval) -> None:
        # Identifiers and states only: arguments are never part of an event.
        payload: dict[str, object] = {
            "approval_id": str(approval.approval_id),
            "state": approval.state.value,
            "caller": approval.binding.caller,
            "tool_name": approval.binding.tool_name,
            **dict(approval.binding.subject),
        }
        if approval.outcome is not None:
            payload["outcome"] = approval.outcome.value
        if approval.task_id is not None:
            payload["task_id"] = str(approval.task_id)
        await self._events.publish(ApprovalEvent(event_type=event_type, source="approval_gateway", payload=payload))


def _resolution(approval: Approval) -> ApprovalResolution:
    return ApprovalResolution(approval_id=approval.approval_id, state=approval.state, operation_digest=approval.operation_digest)
