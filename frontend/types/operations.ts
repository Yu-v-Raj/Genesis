/** Mirrors backend/app/core/api/schemas/operations.py: traces and durable runtime events. */
import type { Approval } from "@/types/approvals";
import type { Execution, ExecutionTransition } from "@/types/executions";
import type { ToolTask } from "@/types/tools";
import type { Workflow } from "@/types/workflows";

/** A persisted event. Its payload was redacted and size-bounded when it was stored. */
export interface RuntimeEvent {
  sequence: number;
  event_id: string;
  event_type: string;
  source: string;
  occurred_at: string;
  payload: Record<string, unknown>;
  execution_id: string | null;
  interaction_id: string | null;
  agent_id: string | null;
  workflow_id: string | null;
  /** A workflow step (never a tool task). */
  step_id: string | null;
  tool_task_id: string | null;
  approval_id: string | null;
}

export interface RuntimeEventPage {
  /** Newest first. */
  events: RuntimeEvent[];
  /** Pass as `before_sequence` to load older events; `null` when there are none. */
  next_before_sequence: number | null;
}

export interface RuntimeEventQuery {
  before_sequence?: number | null;
  limit?: number;
  /** An exact type, or a prefix ending in "." such as "workflow.". */
  event_type?: string | null;
  execution_id?: string | null;
  workflow_id?: string | null;
  approval_id?: string | null;
  tool_task_id?: string | null;
}

/** One model call, from its llm.completed or llm.failed event. Never message content. */
export interface ModelCall {
  sequence: number;
  at: string;
  outcome: "completed" | "failed";
  provider: string | null;
  model: string | null;
  duration_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  error_type: string | null;
  /** Requests made for this call (1 = no retry); absent for calls recorded before retries existed. */
  attempts?: number | null;
  error_category?: string | null;
}

export interface WorkflowTransition {
  sequence: number;
  /** `null`: the run itself changed status. */
  step_id: string | null;
  attempt: number;
  from_status: string | null;
  to_status: string;
  at: string;
  /** The worker holding the run's lease after the change, when one did. */
  worker: string | null;
  detail: string | null;
}

/** True where a list was cut to its most recent entries. */
export interface TraceLimits {
  tool_tasks: boolean;
  approvals: boolean;
  events: boolean;
}

export interface ExecutionTrace {
  execution: Execution;
  transitions: ExecutionTransition[];
  model_calls: ModelCall[];
  tool_tasks: ToolTask[];
  approvals: Approval[];
  /** Oldest first. */
  events: RuntimeEvent[];
  truncated: TraceLimits;
}

export interface WorkflowTrace {
  run: Workflow;
  transitions: WorkflowTransition[];
  tool_tasks: ToolTask[];
  approvals: Approval[];
  /** Oldest first. */
  events: RuntimeEvent[];
  truncated: TraceLimits;
}
