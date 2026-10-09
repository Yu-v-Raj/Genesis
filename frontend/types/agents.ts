import type { RealtimeEvent } from "@/types/realtime";

export type AgentStatus =
  | "created"
  | "initializing"
  | "idle"
  | "running"
  | "waiting"
  | "paused"
  | "completed"
  | "failed"
  | "stopped";

export interface Agent {
  id: string;
  name: string;
  description: string;
  type: string;
  status: AgentStatus;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  tags: string[];
}

export interface AgentContext {
  session_id: string;
  current_state: AgentStatus;
  current_task: string | null;
  temporary_variables: Record<string, unknown>;
  runtime_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ToolActivity {
  tool_name: string;
  status: "running" | "completed" | "failed" | "rejected" | string;
  result: unknown | null;
  error: string | null;
  duration: number | null;
}

export interface AgentChatResponse {
  agent: Agent;
  response: { content: string | null };
  interaction_id: string;
  tool_activities: ToolActivity[];
}

export interface SessionMessage { role: "user" | "assistant" | "tool"; content: string; }
export interface AgentSession { id: string; agent_id: string; messages: SessionMessage[]; }

export interface CreateAgentInput {
  name: string;
  description: string;
  type: string;
  tags: string[];
}

export interface AgentListResponse {
  agents: Agent[];
}

export interface EventListResponse {
  events: RealtimeEvent[];
}
