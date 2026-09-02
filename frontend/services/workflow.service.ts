import { requestJson } from "@/services/api-client";
import type { Workflow, WorkflowCreateRequest, WorkflowListResponse, WorkflowTaskListResponse } from "@/types/workflows";

const WORKFLOW_API_BASE_URL = process.env.NEXT_PUBLIC_WORKFLOW_API_BASE_URL ?? "http://127.0.0.1:8000/api/workflows";

export class WorkflowApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) { super(message); this.name = "WorkflowApiError"; this.status = status; }
}

function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  return requestJson(WORKFLOW_API_BASE_URL, endpoint, init, "Unable to connect to the Genesis Workflow Runtime API.", (message, status) => new WorkflowApiError(message, status));
}

/** Typed REST adapter for the existing dependency-aware Workflow Runtime API. */
export const WorkflowService = Object.freeze({
  list: (): Promise<WorkflowListResponse> => request(""),
  get: (workflowId: string): Promise<Workflow> => request(`/${encodeURIComponent(workflowId)}`),
  create: (input: WorkflowCreateRequest): Promise<Workflow> => request("", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) }),
  delete: (workflowId: string): Promise<Workflow> => request(`/${encodeURIComponent(workflowId)}`, { method: "DELETE" }),
  start: (workflowId: string): Promise<Workflow> => request(`/${encodeURIComponent(workflowId)}/start`, { method: "POST" }),
  pause: (workflowId: string): Promise<Workflow> => request(`/${encodeURIComponent(workflowId)}/pause`, { method: "POST" }),
  resume: (workflowId: string): Promise<Workflow> => request(`/${encodeURIComponent(workflowId)}/resume`, { method: "POST" }),
  cancel: (workflowId: string): Promise<Workflow> => request(`/${encodeURIComponent(workflowId)}/cancel`, { method: "POST" }),
  tasks: (workflowId: string): Promise<WorkflowTaskListResponse> => request(`/${encodeURIComponent(workflowId)}/tasks`),
  history: (workflowId: string): Promise<WorkflowTaskListResponse> => request(`/${encodeURIComponent(workflowId)}/history`),
});
