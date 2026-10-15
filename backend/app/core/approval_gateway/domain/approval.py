"""The contract Tool Runtime uses to ask whether one specific operation is approved.

Milestone 1 defines only this interface. Genesis has no Approval Gateway yet, so no
implementation is wired at startup and every operation that needs approval is held as
``approval_required``. Milestone 2 implements the gateway: who may approve, durable
decisions, expiry, and resuming the exact operation that was approved.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    # No decision exists for this exact operation (the default for everything today).
    NOT_DECIDED = "not_decided"


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalRequest:
    """One operation awaiting a decision.

    An approval must cover exactly this tool, these arguments, and this caller: a decision
    for different arguments or another caller must not be reused.
    """

    caller: str
    tool_name: str
    arguments: Mapping[str, object]
    # Identifiers of the Agent, workflow step, or execution the operation belongs to.
    subject: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        object.__setattr__(self, "subject", MappingProxyType(dict(self.subject)))


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalDecision:
    status: ApprovalStatus
    approval_id: str | None = None

    @property
    def approved(self) -> bool:
        return self.status is ApprovalStatus.APPROVED


class ApprovalGateway(Protocol):
    async def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        """Return the recorded decision for exactly this operation, never a guess."""
        ...
