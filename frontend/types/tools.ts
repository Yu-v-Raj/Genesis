export type ToolStatus = "pending" | "running" | "completed" | "failed" | string;

export interface ToolDefinition {
  name: string;
  description: string;
  version: string;
  capabilities: string[];
  permissions: string[];
  enabled: boolean;
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
}

export interface ToolListResponse { tools: ToolDefinition[]; }
export interface ToolHistoryResponse { tasks: ToolTask[]; }
export interface ToolCapabilitiesResponse { capabilities: string[]; }
export interface ToolExecutionInput {
  tool_name: string;
  arguments: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  execution_id?: string;
}
