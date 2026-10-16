import { requestJson } from "@/services/api-client";
import type { ToolApprovalPending, ToolCapabilitiesResponse, ToolDefinition, ToolExecutionInput, ToolHistoryQuery, ToolHistoryResponse, ToolListResponse, ToolTask } from "@/types/tools";

const TOOL_API_BASE_URL = process.env.NEXT_PUBLIC_TOOL_API_BASE_URL ?? "http://127.0.0.1:8000/api/tools";

export class ToolApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) { super(message); this.name = "ToolApiError"; this.status = status; }
}

function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  return requestJson(TOOL_API_BASE_URL, endpoint, init, "Unable to connect to the Genesis Tool Runtime API.", (message, status) => new ToolApiError(message, status));
}

function pageSearch(query: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  const search = params.toString();
  return search ? `?${search}` : "";
}

/** Typed REST adapter for the existing Genesis Tool Runtime endpoints. */
export const ToolService = Object.freeze({
  list: (): Promise<ToolListResponse> => request(""),
  get: (name: string): Promise<ToolDefinition> => request(`/${encodeURIComponent(name)}`),
  /** Durable tool runs, newest first; page with `before` (from `next_before`). */
  history: (query: ToolHistoryQuery = {}): Promise<ToolHistoryResponse> => request(`/history${pageSearch(query)}`),
  capabilities: (): Promise<ToolCapabilitiesResponse> => request("/capabilities"),
  /** A task, or (HTTP 202) a pending approval request when the call needs the operator's decision. */
  execute: (input: ToolExecutionInput): Promise<ToolTask | ToolApprovalPending> => request("/execute", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }),
});
