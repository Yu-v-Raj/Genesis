class WorkflowRuntimeError(Exception): pass
class WorkflowNotFoundError(WorkflowRuntimeError): pass
class WorkflowValidationError(WorkflowRuntimeError): pass
class WorkflowLifecycleError(WorkflowRuntimeError): pass
class WorkflowRetryError(WorkflowRuntimeError):
    """Raised when a run cannot be retried, or needs explicit confirmation first."""
    def __init__(self, message: str, *, requires_acknowledgement: bool = False) -> None:
        super().__init__(message)
        self.requires_acknowledgement = requires_acknowledgement
