"""Exceptions raised by the Genesis Workflow Engine."""


class WorkflowEngineError(Exception):
    """Base exception for Workflow Engine failures."""


class DuplicateWorkflowError(WorkflowEngineError):
    """Raised when a workflow name is registered more than once."""

    def __init__(self, workflow_name: str) -> None:
        super().__init__(f"A workflow named {workflow_name!r} is already registered.")


class WorkflowNotFoundError(WorkflowEngineError):
    """Raised when a requested workflow name is not registered."""

    def __init__(self, workflow_name: str) -> None:
        super().__init__(f"No workflow named {workflow_name!r} is registered.")


class InvalidWorkflowNameError(WorkflowEngineError):
    """Raised when a workflow name is empty or not a string."""
