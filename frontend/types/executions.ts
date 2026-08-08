export type ExecutionStatus =
  | "pending"
  | "queued"
  | "starting"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

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
  metadata: Record<string, unknown>;
}

export interface ExecutionListResponse {
  executions: Execution[];
}

export interface ExecuteAgentInput {
  metadata?: Record<string, unknown>;
}
