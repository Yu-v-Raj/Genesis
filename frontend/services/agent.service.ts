import type {
  Agent,
  AgentContext,
  AgentListResponse,
  CreateAgentInput,
} from "@/types/agents";
import { requestJson } from "@/services/api-client";

const AGENT_API_BASE_URL =
  process.env.NEXT_PUBLIC_AGENT_API_BASE_URL ?? "http://127.0.0.1:8000/api/agents";

export class AgentApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "AgentApiError";
    this.status = status;
  }
}

async function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  return requestJson(
    AGENT_API_BASE_URL,
    endpoint,
    init,
    "Unable to connect to the Genesis Agent Runtime API.",
    (message, status) => new AgentApiError(message, status)
  );
}

function lifecycle(agentId: string, operation: "initialize" | "start" | "pause" | "resume" | "stop"): Promise<Agent> {
  return request<Agent>(`/${agentId}/${operation}`, { method: "POST" });
}

/** Typed transport adapter for the Genesis Agent Runtime API. */
export const AgentService = Object.freeze({
  list: (): Promise<AgentListResponse> => request<AgentListResponse>(""),
  get: (agentId: string): Promise<Agent> => request<Agent>(`/${agentId}`),
  create: (input: CreateAgentInput): Promise<Agent> =>
    request<Agent>("", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  delete: (agentId: string): Promise<Agent> => request<Agent>(`/${agentId}`, { method: "DELETE" }),
  initialize: (agentId: string): Promise<Agent> => lifecycle(agentId, "initialize"),
  start: (agentId: string): Promise<Agent> => lifecycle(agentId, "start"),
  pause: (agentId: string): Promise<Agent> => lifecycle(agentId, "pause"),
  resume: (agentId: string): Promise<Agent> => lifecycle(agentId, "resume"),
  stop: (agentId: string): Promise<Agent> => lifecycle(agentId, "stop"),
  getContext: (agentId: string): Promise<AgentContext> => request<AgentContext>(`/${agentId}/context`),
});
