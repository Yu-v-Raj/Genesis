import { eventsSearch } from "@/lib/traces";
import { requestJson } from "@/services/api-client";
import type { ExecutionTrace, RuntimeEventPage, RuntimeEventQuery, WorkflowTrace } from "@/types/operations";

const OPERATIONS_API_BASE_URL = process.env.NEXT_PUBLIC_OPERATIONS_API_BASE_URL ?? "http://127.0.0.1:8000/api/operations";

export class OperationsApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) { super(message); this.name = "OperationsApiError"; this.status = status; }
}

function request<T>(endpoint: string): Promise<T> {
  return requestJson(OPERATIONS_API_BASE_URL, endpoint, {}, "Unable to connect to the Genesis Operations API.", (message, status) => new OperationsApiError(message, status));
}

/** Read-only adapter: nothing here changes state on the server. */
export const OperationsService = Object.freeze({
  events: (query: RuntimeEventQuery = {}): Promise<RuntimeEventPage> => request(`/events${eventsSearch(query)}`),
  executionTrace: (executionId: string): Promise<ExecutionTrace> => request(`/executions/${encodeURIComponent(executionId)}/trace`),
  workflowTrace: (workflowId: string): Promise<WorkflowTrace> => request(`/workflows/${encodeURIComponent(workflowId)}/trace`),
});
