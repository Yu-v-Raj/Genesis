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
  llm_model: LLMModelRef | null;
  allowed_tools: string[];
  instructions: string;
}

/** An LLM model as reported by the backend LLM Runtime (credentials never included). */
export interface LLMModelOption {
  provider: string;
  model_name: string;
  capabilities: string[];
  metadata: { configured?: boolean } & Record<string, unknown>;
}

export interface LLMModelRef {
  provider: string;
  model_name: string;
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
  response: { content: string | null; finish_reason: string | null };
  interaction_id: string;
  session_id: string | null;
  tool_activities: ToolActivity[];
}

export interface SessionMessage {
  role: "user" | "assistant" | "tool";
  content: string;
  interaction_id: string | null;
  tool_name: string | null;
  tool_status: string | null;
  tool_calls: string[];
}
export interface AgentSession {
  id: string;
  agent_id: string;
  created_at: string;
  updated_at: string;
  messages: SessionMessage[];
}

/** A stored conversation, without its messages. */
export interface AgentSessionSummary {
  id: string;
  agent_id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  title: string | null;
}

export interface AgentSessionList {
  active_session_id: string | null;
  sessions: AgentSessionSummary[];
}

export interface AgentConfigurationInput {
  llm_model: LLMModelRef | null;
  allowed_tools: string[];
  instructions: string;
}

export interface CreateAgentInput extends AgentConfigurationInput {
  name: string;
  description: string;
  type: string;
  tags: string[];
  initialize: boolean;
}

export interface AgentListResponse {
  agents: Agent[];
}

export interface EventListResponse {
  events: RealtimeEvent[];
}
