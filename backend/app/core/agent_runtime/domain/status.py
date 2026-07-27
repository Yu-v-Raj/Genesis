"""Lifecycle states for Genesis Agent Runtime records."""

from enum import StrEnum


class AgentStatus(StrEnum):
    """The lifecycle state of an Agent process record."""

    CREATED = "created"
    INITIALIZING = "initializing"
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
