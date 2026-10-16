"""Adapts the Approval Gateway to the Execution Runtime's ``ResumeGate`` port."""

from uuid import UUID

from backend.app.core.approval_gateway.application.approval_service import ApprovalService
from backend.app.core.approval_gateway.domain.approval import ApprovalState


class ApprovalResumeGate:
    """A suspended execution may resume once its request is no longer pending (approved,
    rejected, expired, cancelled, or unknown); the handler decides what that means."""

    def __init__(self, approvals: ApprovalService) -> None:
        self._approvals = approvals

    async def is_resolved(self, token: str) -> bool:
        approval_id = _uuid(token)
        if approval_id is None:
            return True  # an unreadable token can never be approved; let the work fail closed
        return await self._approvals.state_of(approval_id) is not ApprovalState.PENDING

    async def abandon(self, token: str, reason: str) -> None:
        approval_id = _uuid(token)
        if approval_id is not None:
            await self._approvals.cancel(approval_id, reason=reason)


def _uuid(token: str) -> UUID | None:
    try:
        return UUID(token)
    except ValueError:
        return None
