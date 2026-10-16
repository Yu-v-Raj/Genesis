export type ToolStatus = "pending" | "running" | "completed" | "failed" | string;

export interface ToolDefinition {
  name: string;
  description: string;
  version: string;
  capabilities: string[];
  permissions: string[];
  enabled: boolean;
  /** Declared by the tool: whether running it may change something outside Genesis. */
  side_effects: boolean;
  metadata: Record<string, unknown>;
}

export interface ToolResult {
  status: ToolStatus;
  output: unknown | null;
  logs: string[];
  metadata: Record<string, unknown>;
  duration: number;
  error: string | null;
}

export interface ToolTask {
  task_id: string;
  execution_id: string | null;
  tool_name: string;
  status: ToolStatus;
  started_at: string | null;
  finished_at: string | null;
  metadata: Record<string, unknown>;
  result: ToolResult | null;
  created_at?: string | null;
  tool_version?: string | null;
  /** A display copy with secret-looking fields replaced; never the raw arguments. */
  arguments?: Record<string, unknown>;
}

export interface ToolListResponse { tools: ToolDefinition[]; }
export interface ToolHistoryResponse {
  /** Newest first, from durable history. */
  tasks: ToolTask[];
  /** Pass as `before` to load older runs; an opaque cursor; `null` when there are none. */
  next_before?: string | null;
}
export interface ToolHistoryQuery {
  before?: string | null;
  limit?: number;
  tool_name?: string | null;
  execution_id?: string | null;
  workflow_id?: string | null;
}
export interface ToolCapabilitiesResponse { capabilities: string[]; }
export interface ToolExecutionInput {
  tool_name: string;
  arguments: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  execution_id?: string;
}

/** The server held an operator test for approval (HTTP 202); nothing ran. */
export interface ToolApprovalPending {
  detail: string;
  outcome: "approval_required";
  reason: string | null;
  approval_id: string;
}
