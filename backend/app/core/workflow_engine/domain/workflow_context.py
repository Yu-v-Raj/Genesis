"""Execution context shared by sequential Genesis workflow steps."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class WorkflowContext:
    """Mutable, application-agnostic data shared across workflow steps."""

    data: dict[str, object] = field(default_factory=dict)
