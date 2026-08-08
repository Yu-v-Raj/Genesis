"""Lifecycle states for individual execution records."""

from enum import StrEnum


class ExecutionStatus(StrEnum):
    """The lifecycle state of a single execution, independent of its Agent."""

    PENDING = "pending"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
