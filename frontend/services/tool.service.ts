import { requestJson } from "@/services/api-client";
import type { ToolCapabilitiesResponse, ToolDefinition, ToolExecutionInput, ToolHistoryResponse, ToolListResponse, ToolTask } from "@/types/tools";

const TOOL_API_BASE_URL = process.env.NEXT_PUBLIC_TOOL_API_BASE_URL ?? "http://127.0.0.1:8000/api/tools";

export class ToolApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) { super(message); this.name = "ToolApiError"; this.status = status; }
}

function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  return requestJson(TOOL_API_BASE_URL, endpoint, init, "Unable to connect to the Genesis Tool Runtime API.", (message, status) => new ToolApiError(message, status));
}

/** Typed REST adapter for the existing Genesis Tool Runtime endpoints. */
export const ToolService = Object.freeze({
  list: (): Promise<ToolListResponse> => request(""),
  get: (name: string): Promise<ToolDefinition> => request(`/${encodeURIComponent(name)}`),
  history: (): Promise<ToolHistoryResponse> => request("/history"),
  capabilities: (): Promise<ToolCapabilitiesResponse> => request("/capabilities"),
  execute: (input: ToolExecutionInput): Promise<ToolTask> => request("/execute", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input),
  }),
});
