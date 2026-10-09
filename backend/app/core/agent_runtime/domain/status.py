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


def restoration_status(status: AgentStatus) -> AgentStatus:
    """Collapse a live status into what is stored and restored after a restart.

    In-flight states (RUNNING, PAUSED, ...) describe work that does not survive a restart,
    so they are stored as IDLE: the Agent is re-initialized and simply available again.
    """
    if status in {AgentStatus.CREATED, AgentStatus.INITIALIZING}:
        return AgentStatus.CREATED
    if status is AgentStatus.STOPPED:
        return AgentStatus.STOPPED
    return AgentStatus.IDLE
