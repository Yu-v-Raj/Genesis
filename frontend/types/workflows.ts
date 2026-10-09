import type { RetryInfo } from "@/types/executions";
import type { RealtimeEvent } from "@/types/realtime";

export type WorkflowStatus = "created" | "queued" | "running" | "paused" | "completed" | "failed" | "cancelled" | "interrupted";
export type WorkflowTaskStatus = "pending" | "ready" | "running" | "completed" | "failed" | "cancelled" | "blocked" | "interrupted";

export interface WorkflowTask {
  task_id: string;
  workflow_id: string | null;
  name: string;
  action: "tool";
  configuration: { tool_name: string; tool_arguments: Record<string, unknown> };
  dependencies: string[];
  status: WorkflowTaskStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: unknown | null;
  error: string | null;
  metadata: Record<string, unknown>;
}

export interface WorkflowDefinition {
  name: string;
  description: string;
  metadata: Record<string, unknown>;
  tasks: WorkflowTaskCreateInput[];
}

export interface WorkflowTaskCreateInput {
  task_id: string;
  name: string;
  action?: "tool";
  tool_name: string;
  tool_arguments?: Record<string, unknown>;
  dependencies?: string[];
  metadata?: Record<string, unknown>;
}

/** One run of a workflow definition version. */
export interface Workflow extends Omit<WorkflowDefinition, "tasks"> {
  workflow_id: string;
  status: WorkflowStatus;
  created_at: string;
  updated_at: string;
  tasks: WorkflowTask[];
  definition_id: string | null;
  definition_version: number | null;
  attempt: number;
  error: string | null;
  retry: RetryInfo | null;
}

/** A stored, versioned workflow plan (latest version unless a version is requested). */
export interface StoredWorkflowDefinition {
  definition_id: string;
  version: number;
  name: string;
  description: string;
  metadata: Record<string, unknown>;
  created_at: string;
  tasks: { task_id: string; name: string; action: string; configuration: Record<string, unknown>; dependencies: string[] }[];
}

export interface WorkflowDefinitionListResponse { definitions: StoredWorkflowDefinition[]; }

export interface WorkflowResult {
  completed_tasks: number;
  failed_tasks: number;
  output: Record<string, unknown>;
  errors: Record<string, string>;
}

/** The current API returns task snapshots for both /tasks and /history. */
export interface WorkflowHistoryItem {
  id: string;
  event: "task";
  timestamp: string;
  workflow_id: string | null;
  task_id: string;
  task_name: string;
  status: WorkflowTaskStatus;
  result: unknown | null;
  error: string | null;
}

export interface WorkflowListResponse { workflows: Workflow[]; }
export interface WorkflowTaskListResponse { tasks: WorkflowTask[]; }
export type WorkflowCreateRequest = WorkflowDefinition;
export type WorkflowCreateResponse = Workflow;
export type WorkflowEvent = RealtimeEvent;
