"""Approval Gateway domain: durable, single-use permission for one exact tool operation.

An approval authorizes one *operation*, not a tool. The operation is the tool's
identity, its schema, the canonical arguments, and the caller with its real identifiers
(the Agent and execution, or the workflow run, step and attempt). Those values are hashed
into ``operation_digest``; an approval is only ever looked up and consumed by that digest,
so changing anything about the operation makes the old approval inapplicable.

```text
                 approve                      consume (exactly once, atomically)
    PENDING ───────────────▶ APPROVED ───────────────────────────▶ CONSUMED
       │  \\ reject               │  \\                                 (outcome recorded
       │   ▶ REJECTED             │   ▶ EXPIRED (deadline passed)       after the tool ran)
       │                          ▼
       ├──▶ EXPIRED           CANCELLED (the operation was abandoned or is no
       └──▶ CANCELLED                    longer allowed before it ran)
```

A decision is not an execution: an APPROVED request may still expire or be cancelled,
and a CONSUMED one may have run and failed. ``outcome`` records what happened.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol
from uuid import UUID, uuid4


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    CANCELLED = "cancelled"


# A pending or approved request still stands for its operation; at most one per digest.
ACTIVE_STATES = frozenset({ApprovalState.PENDING, ApprovalState.APPROVED})
FINAL_STATES = frozenset({ApprovalState.REJECTED, ApprovalState.EXPIRED, ApprovalState.CONSUMED, ApprovalState.CANCELLED})

ALLOWED_TRANSITIONS: Mapping[ApprovalState, frozenset[ApprovalState]] = MappingProxyType({
    ApprovalState.PENDING: frozenset({ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.EXPIRED, ApprovalState.CANCELLED}),
    ApprovalState.APPROVED: frozenset({ApprovalState.CONSUMED, ApprovalState.EXPIRED, ApprovalState.CANCELLED}),
    **{state: frozenset() for state in FINAL_STATES},
})


class ApprovalOutcome(StrEnum):
    """What happened after a CONSUMED approval let its operation run."""

    COMPLETED = "completed"
    FAILED = "failed"
    # The process stopped (or the caller was cancelled) while the tool ran: any external
    # effect is unknown, so nothing is re-run automatically.
    UNKNOWN = "unknown"


class DecisionSource(StrEnum):
    """Where a decision came from. Genesis has no accounts: neither of these identifies a
    person, only the local channel the request arrived through."""

    LOCAL_CONSOLE = "local_operator_console"
    LOCAL_API = "local_api_client"
    SYSTEM = "system"  # expiry, or the operation being abandoned


class ApprovalError(Exception):
    """Base error for approval operations; messages are safe to show."""


class ApprovalNotFoundError(ApprovalError):
    def __init__(self, approval_id: UUID) -> None:
        super().__init__(f"Approval request {approval_id} was not found.")


class ApprovalTransitionError(ApprovalError):
    """The requested change isn't allowed from the request's current state."""

    def __init__(self, current: ApprovalState, target: ApprovalState) -> None:
        super().__init__(_TRANSITION_MESSAGES.get((current, target), f"This request is {current.value}; it can't become {target.value}."))
        self.current = current
        self.target = target


_TRANSITION_MESSAGES = {
    (ApprovalState.APPROVED, ApprovalState.APPROVED): "This request was already approved.",
    (ApprovalState.REJECTED, ApprovalState.APPROVED): "This request was rejected; it can't be approved.",
    (ApprovalState.EXPIRED, ApprovalState.APPROVED): "This request expired before it was decided.",
    (ApprovalState.CONSUMED, ApprovalState.APPROVED): "This approval was already used.",
    (ApprovalState.CANCELLED, ApprovalState.APPROVED): "This request was cancelled; its operation no longer exists.",
}


# ----------------------------------------------------------------------- binding


def canonical_json(value: object) -> str:
    """Deterministic JSON in which 1, 1.0 and true stay different values.

    Mappings become sorted objects and tuples become lists; NaN, infinity and anything
    that isn't plain JSON raise ``ValueError``.
    """

    def plain(item: object) -> object:
        if isinstance(item, Mapping):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("Operation keys must be strings.")
            return {key: plain(inner) for key, inner in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(inner) for inner in item]
        if item is None or isinstance(item, (str, bool, int, float)):
            return item
        raise ValueError(f"Operation values must be plain JSON, not {type(item).__name__}.")

    try:
        return json.dumps(plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError) as error:
        raise ValueError(str(error)) from error


@dataclass(frozen=True, slots=True, kw_only=True)
class OperationBinding:
    """Everything that defines one operation. Two operations share a digest only if all
    of these are identical."""

    caller: str
    # The caller's real identifiers: agent_id/execution_id, or workflow_id/workflow_task_id/
    # workflow_attempt. Operator test runs have none.
    subject: Mapping[str, str]
    tool_name: str
    tool_version: str
    # Hash of the tool's declared parameter schema and policy-relevant declarations.
    tool_contract: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject", MappingProxyType(dict(self.subject)))
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        canonical_json(self.arguments)  # fail now, not when the digest is needed

    @property
    def digest(self) -> str:
        document = {
            "caller": self.caller,
            "subject": dict(self.subject),
            "tool": {"name": self.tool_name, "version": self.tool_version, "contract": self.tool_contract},
            "arguments": dict(self.arguments),
        }
        return hashlib.sha256(canonical_json(document).encode()).hexdigest()


def tool_contract_digest(parameters: Mapping[str, object], *, side_effects: object, permissions: tuple[str, ...]) -> str:
    """Identify a tool's declared contract; a schema or declaration change voids old approvals."""
    document = {"parameters": parameters, "side_effects": side_effects, "permissions": list(permissions)}
    return hashlib.sha256(canonical_json(document).encode()).hexdigest()[:32]


# ----------------------------------------------------------------------- entity


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True, kw_only=True)
class Approval:
    binding: OperationBinding
    expires_at: datetime
    # Why approval is needed, in words safe to show (never derived from the arguments).
    reason: str
    approval_id: UUID = field(default_factory=uuid4)
    state: ApprovalState = ApprovalState.PENDING
    operation_digest: str = ""
    created_at: datetime = field(default_factory=utc_now)
    decided_at: datetime | None = None
    decision_source: DecisionSource | None = None
    consumed_at: datetime | None = None
    task_id: UUID | None = None
    outcome: ApprovalOutcome | None = None
    # Why it was cancelled or expired, or what went wrong after consumption.
    detail: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if not self.operation_digest:
            object.__setattr__(self, "operation_digest", self.binding.digest)
        elif self.operation_digest != self.binding.digest:
            raise ValueError("Stored approval no longer matches its operation; refusing to load it.")

    def is_expired(self, now: datetime) -> bool:
        return self.state in ACTIVE_STATES and now >= self.expires_at

    def transition(self, target: ApprovalState, **changes: object) -> "Approval":
        """Return the request in ``target``; refuses any change the lifecycle doesn't allow."""
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise ApprovalTransitionError(self.state, target)
        return replace(self, state=target, **changes)

    def transition_outcome(self, *, task_id: UUID | None, outcome: ApprovalOutcome, detail: str | None) -> "Approval":
        """Record what happened after consumption; only once, and only on a CONSUMED request."""
        if self.state is not ApprovalState.CONSUMED or self.outcome is not None:
            raise ApprovalError("An outcome can only be recorded once, after the approval was used.")
        return replace(self, task_id=task_id, outcome=outcome, detail=detail if detail is not None else self.detail)


# ------------------------------------------------- contract used by the tool policy


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovalResolution:
    """The gateway's answer for one operation: the request that stands for it right now."""

    approval_id: UUID
    state: ApprovalState
    operation_digest: str

    @property
    def approved(self) -> bool:
        return self.state is ApprovalState.APPROVED


class ApprovalGateway(Protocol):
    async def resolve(self, binding: OperationBinding, *, reason: str) -> ApprovalResolution:
        """Return the active request for exactly this operation, creating a PENDING one if
        none exists. Never approves anything and never consumes."""
        ...

    async def consume(self, approval_id: UUID, operation_digest: str) -> bool:
        """Atomically move an APPROVED, unexpired request for this digest to CONSUMED.
        True for exactly one caller; False if it was used, changed, expired or cancelled."""
        ...

    async def record_outcome(self, approval_id: UUID, *, task_id: UUID | None, outcome: ApprovalOutcome, detail: str | None = None) -> None:
        ...

    async def state_of(self, approval_id: UUID) -> ApprovalState | None:
        """Current state (applying expiry), or None for an unknown request."""
        ...

    async def cancel(self, approval_id: UUID, *, reason: str) -> None:
        """Cancel a request whose operation was abandoned; no-op if it is already final."""
        ...


# ------------------------------------------------------------------------ display


_SECRET_KEY = re.compile(r"(pass(word|phrase)?|secret|token|api[_-]?key|apikey|auth|credential|private[_-]?key|cookie|session[_-]?id|bearer)", re.I)
_SECRET_VALUE = re.compile(r"^(sk-[A-Za-z0-9_\-]{12,}|AIza[0-9A-Za-z_\-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abpr]-[A-Za-z0-9\-]{10,}|Bearer\s+\S{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----.*)$", re.S)
REDACTED = "[redacted]"


def redact_arguments(arguments: Mapping[str, object]) -> tuple[dict[str, object], tuple[str, ...]]:
    """A display copy with secret-looking fields replaced, plus the paths that were redacted.

    The stored operation keeps the exact values (they are what was approved); only what is
    shown to people and sent to the browser is redacted.
    """
    redacted: list[str] = []

    def walk(value: object, path: str) -> object:
        if isinstance(value, Mapping):
            out: dict[str, object] = {}
            for key, inner in value.items():
                child = f"{path}.{key}" if path else str(key)
                if _SECRET_KEY.search(str(key)) and inner not in (None, "", [], {}):
                    out[str(key)] = REDACTED
                    redacted.append(child)
                else:
                    out[str(key)] = walk(inner, child)
            return out
        if isinstance(value, (list, tuple)):
            return [walk(inner, f"{path}[{index}]") for index, inner in enumerate(value)]
        if isinstance(value, str) and _SECRET_VALUE.match(value.strip()):
            redacted.append(path or "(value)")
            return REDACTED
        return value

    shown = walk(arguments, "")
    return (shown if isinstance(shown, dict) else {}), tuple(redacted)
