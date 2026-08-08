"""Typed, in-process events emitted by Genesis Core services."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Mapping
from uuid import uuid4


LOG_CREATED_EVENT_TYPE = "log.created"

@dataclass(frozen=True, slots=True, kw_only=True)
class Event:
    """Immutable event envelope shared by all Genesis observability events."""

    event_type: str
    source: str = "genesis"
    payload: Mapping[str, object] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def name(self) -> str:
        """Return the legacy event name alias for existing Core consumers."""
        return self.event_type


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemStarted(Event):
    """Published when the Genesis runtime has started."""

    event_type: str = field(init=False, default="system.started")


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemStopped(Event):
    """Published when the Genesis runtime has stopped."""

    event_type: str = field(init=False, default="system.stopped")


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceRegistered(Event):
    """Published when a Core service is registered."""

    event_type: str = field(init=False, default="service.registered")


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceRemoved(Event):
    """Published when a Core service is removed."""

    event_type: str = field(init=False, default="service.removed")


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginLoaded(Event):
    """Published when a plugin is initialized."""

    event_type: str = field(init=False, default="plugin.loaded")


@dataclass(frozen=True, slots=True, kw_only=True)
class PluginUnloaded(Event):
    """Published when a plugin is shut down."""

    event_type: str = field(init=False, default="plugin.unloaded")


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolRegistered(Event):
    """Published when a tool is registered."""

    event_type: str = field(init=False, default="tool.registered")


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowRegistered(Event):
    """Published when a workflow is registered."""

    event_type: str = field(init=False, default="workflow.registered")


@dataclass(frozen=True, slots=True, kw_only=True)
class MemoryProviderRegistered(Event):
    """Published when a memory provider is registered."""

    event_type: str = field(init=False, default="memory_provider.registered")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentRegistered(Event):
    """Published when an Agent Runtime record is registered."""

    event_type: str = field(init=False, default="agent.registered")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentRemoved(Event):
    """Published when an Agent Runtime record is removed."""

    event_type: str = field(init=False, default="agent.removed")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentStatusChanged(Event):
    """Published when an Agent Runtime lifecycle status changes."""

    event_type: str = field(init=False, default="agent.status_changed")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentMetadataUpdated(Event):
    """Published when Agent Runtime metadata is updated."""

    event_type: str = field(init=False, default="agent.metadata_updated")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentCreated(Event):
    """Published when the Agent Manager creates a runtime record."""

    event_type: str = field(init=False, default="agent.created")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentInitialized(Event):
    """Published when an Agent reaches its initialized idle state."""

    event_type: str = field(init=False, default="agent.initialized")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentStarted(Event):
    """Published when an Agent enters RUNNING."""

    event_type: str = field(init=False, default="agent.started")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentPaused(Event):
    """Published when an Agent enters PAUSED."""

    event_type: str = field(init=False, default="agent.paused")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentResumed(Event):
    """Published when an Agent resumes RUNNING."""

    event_type: str = field(init=False, default="agent.resumed")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentCompleted(Event):
    """Published when an Agent enters COMPLETED."""

    event_type: str = field(init=False, default="agent.completed")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentFailed(Event):
    """Published when an Agent enters FAILED."""

    event_type: str = field(init=False, default="agent.failed")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentStopped(Event):
    """Published when an Agent enters STOPPED."""

    event_type: str = field(init=False, default="agent.stopped")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentDeleted(Event):
    """Published when the Agent Manager deletes a runtime record."""

    event_type: str = field(init=False, default="agent.deleted")


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentContextUpdated(Event):
    """Published when an Agent's runtime-only context changes."""

    event_type: str = field(init=False, default="agent.context_updated")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionCreated(Event):
    """Published when an execution record is created."""

    event_type: str = field(init=False, default="execution.created")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionQueued(Event):
    """Published when an execution is placed in the executor queue."""

    event_type: str = field(init=False, default="execution.queued")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionStarted(Event):
    """Published when deterministic execution work begins."""

    event_type: str = field(init=False, default="execution.started")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionProgress(Event):
    """Published when an execution reaches a meaningful runtime step."""

    event_type: str = field(init=False, default="execution.progress")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionCompleted(Event):
    """Published when an execution succeeds."""

    event_type: str = field(init=False, default="execution.completed")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionFailed(Event):
    """Published when an execution fails."""

    event_type: str = field(init=False, default="execution.failed")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutionCancelled(Event):
    """Published when an execution is cancelled."""

    event_type: str = field(init=False, default="execution.cancelled")


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskStarted(Event):
    """Published when a future runtime task begins."""

    event_type: str = field(init=False, default="task.started")


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskFinished(Event):
    """Published when a future runtime task completes."""

    event_type: str = field(init=False, default="task.finished")


@dataclass(frozen=True, slots=True, kw_only=True)
class ErrorOccurred(Event):
    """Published when a Core operation encounters an error."""

    event_type: str = field(init=False, default="error.occurred")


@dataclass(frozen=True, slots=True, kw_only=True)
class Heartbeat(Event):
    """Published periodically while the Genesis runtime is active."""

    event_type: str = field(init=False, default="system.heartbeat")


@dataclass(frozen=True, slots=True, kw_only=True)
class LogCreated(Event):
    """Published after a structured Genesis log record is written."""

    event_type: str = field(init=False, default=LOG_CREATED_EVENT_TYPE)
