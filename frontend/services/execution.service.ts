import { requestJson } from "@/services/api-client";
import type { ExecuteAgentInput, Execution, ExecutionListResponse } from "@/types/executions";

const EXECUTION_API_BASE_URL =
  process.env.NEXT_PUBLIC_EXECUTION_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export class ExecutionApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ExecutionApiError";
    this.status = status;
  }
}

function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  return requestJson(
    EXECUTION_API_BASE_URL,
    endpoint,
    init,
    "Unable to connect to the Genesis Execution Runtime API.",
    (message, status) => new ExecutionApiError(message, status)
  );
}

/** Typed transport adapter for the existing Genesis Execution Runtime API. */
export const ExecutionService = Object.freeze({
  list: (): Promise<ExecutionListResponse> => request<ExecutionListResponse>("/executions"),
  get: (executionId: string): Promise<Execution> => request<Execution>(`/executions/${executionId}`),
  listForAgent: (agentId: string): Promise<ExecutionListResponse> =>
    request<ExecutionListResponse>(`/agents/${agentId}/executions`),
  execute: (agentId: string, input: ExecuteAgentInput = {}): Promise<Execution> =>
    request<Execution>(`/agents/${agentId}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  cancel: (executionId: string): Promise<Execution> =>
    request<Execution>(`/executions/${executionId}/cancel`, { method: "POST" }),
});
