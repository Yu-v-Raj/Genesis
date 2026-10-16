import { requestJson } from "@/services/api-client";
import type { Approval, ApprovalActionResponse, ApprovalListResponse } from "@/types/approvals";

const APPROVAL_API_BASE_URL = process.env.NEXT_PUBLIC_APPROVAL_API_BASE_URL ?? "http://127.0.0.1:8000/api/approvals";

export class ApprovalApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) { super(message); this.name = "ApprovalApiError"; this.status = status; }
}

function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  return requestJson(APPROVAL_API_BASE_URL, endpoint, init, "Unable to connect to the Genesis Approval Gateway.", (message, status) => new ApprovalApiError(message, status));
}

const post = (id: string, action: string) => request<ApprovalActionResponse>(`/${encodeURIComponent(id)}/${action}`, { method: "POST" });

/** Typed REST adapter for the Approval Gateway. Every decision is validated by the server. */
export const ApprovalService = Object.freeze({
  list: (limit = 200): Promise<ApprovalListResponse> => request(`?limit=${limit}`),
  get: (id: string): Promise<Approval> => request(`/${encodeURIComponent(id)}`),
  approve: (id: string) => post(id, "approve"),
  reject: (id: string) => post(id, "reject"),
  cancel: (id: string) => post(id, "cancel"),
  run: (id: string) => post(id, "run"),
});
