/** Mirrors backend/app/core/api/schemas/approvals.py. Arguments are always the redacted copy. */

export type ApprovalState = "pending" | "approved" | "rejected" | "expired" | "consumed" | "cancelled";
export type ApprovalCaller = "agent" | "workflow" | "operator";

export interface ApprovalSubject {
  agent_id: string | null;
  agent_name: string | null;
  execution_id: string | null;
  workflow_id: string | null;
  workflow_name: string | null;
  step_id: string | null;
  step_name: string | null;
  attempt: number | null;
}

export interface Approval {
  approval_id: string;
  state: ApprovalState;
  caller: ApprovalCaller | string;
  tool_name: string;
  tool_description: string | null;
  tool_version: string;
  reason: string;
  arguments: Record<string, unknown>;
  redacted_fields: string[];
  subject: ApprovalSubject;
  created_at: string;
  expires_at: string;
  decided_at: string | null;
  decision_source: string | null;
  consumed_at: string | null;
  task_id: string | null;
  outcome: "completed" | "failed" | "unknown" | null;
  detail: string | null;
  can_decide: boolean;
  can_cancel: boolean;
  can_run: boolean;
}

export interface ApprovalListResponse {
  approvals: Approval[];
  pending_count: number;
}

export interface ApprovalActionResponse {
  approval: Approval;
  task: import("./tools").ToolTask | null;
  problem: string | null;
}
