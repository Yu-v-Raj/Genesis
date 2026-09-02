"""Workflow Runtime events carried by the shared Genesis EventBus."""

from dataclasses import dataclass

from backend.app.core.observability.domain.events import Event


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowEvent(Event):
    """Typed envelope for the explicit Workflow Runtime lifecycle event names."""
