"""Lifecycle states for individual execution records."""

from enum import StrEnum


class ExecutionStatus(StrEnum):
    """The lifecycle state of a single execution, independent of its Agent.

    ``INTERRUPTED`` means the process running the work stopped after the work may have
    begun, so its outcome is unknown. It is terminal; a retry is a new linked attempt.
    """

    PENDING = "pending"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
