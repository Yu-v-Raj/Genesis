export type ExecutionStatus =
  | "pending"
  | "queued"
  | "starting"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  /** The process stopped while the work was running; its outcome is unknown. */
  | "interrupted";

/** Server-computed retry eligibility; the UI never decides this itself. */
export interface RetryInfo {
  allowed: boolean;
  requires_acknowledgement: boolean;
  reason: string;
}

export interface ExecutionResult {
  status: ExecutionStatus;
  output: string | null;
  duration: number | null;
  logs: string[];
  metadata: Record<string, unknown>;
}

export interface Execution {
  execution_id: string;
  agent_id: string;
  status: ExecutionStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration: number | null;
  result: ExecutionResult | null;
  error: string | null;
  error_category: string | null;
  current_step: string | null;
  updated_at: string | null;
  attempt: number;
  retry_of: string | null;
  retry: RetryInfo | null;
  metadata: Record<string, unknown>;
}

export interface ExecutionTransition {
  sequence: number;
  from_status: ExecutionStatus | null;
  to_status: ExecutionStatus;
  at: string;
  detail: string | null;
}

export interface ExecutionHistoryResponse {
  execution_id: string;
  transitions: ExecutionTransition[];
}

export interface ExecutionListResponse {
  executions: Execution[];
}

export interface ExecuteAgentInput {
  metadata?: Record<string, unknown>;
}
