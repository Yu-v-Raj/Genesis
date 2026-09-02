class WorkflowRuntimeError(Exception): pass
class WorkflowNotFoundError(WorkflowRuntimeError): pass
class WorkflowValidationError(WorkflowRuntimeError): pass
class WorkflowLifecycleError(WorkflowRuntimeError): pass
