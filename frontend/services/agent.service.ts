import type {
  Agent,
  AgentContext,
  AgentListResponse,
  CreateAgentInput,
  AgentConfigurationInput,
  LLMModelOption,
  AgentChatResponse,
  AgentSession,
} from "@/types/agents";
import { requestJson } from "@/services/api-client";

const AGENT_API_BASE_URL =
  process.env.NEXT_PUBLIC_AGENT_API_BASE_URL ?? "http://127.0.0.1:8000/api/agents";
const LLM_API_BASE_URL =
  process.env.NEXT_PUBLIC_LLM_API_BASE_URL ?? "http://127.0.0.1:8000/api/llm";

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

// RUNNING is owned by conversations, so the UI only drives initialize and stop.
function lifecycle(agentId: string, operation: "initialize" | "stop"): Promise<Agent> {
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
  stop: (agentId: string): Promise<Agent> => lifecycle(agentId, "stop"),
  updateConfiguration: (agentId: string, input: Partial<AgentConfigurationInput>): Promise<Agent> =>
    request<Agent>(`/${agentId}/configuration`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  models: (): Promise<{ models: LLMModelOption[] }> =>
    requestJson(
      LLM_API_BASE_URL,
      "/models",
      {},
      "Unable to connect to the Genesis LLM Runtime API.",
      (message, status) => new AgentApiError(message, status)
    ),
  getContext: (agentId: string): Promise<AgentContext> => request<AgentContext>(`/${agentId}/context`),
  getSession: (agentId: string): Promise<AgentSession> => request<AgentSession>(`/${agentId}/session`),
  chat: (agentId: string, message: string): Promise<AgentChatResponse> => request<AgentChatResponse>(`/${agentId}/chat`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message }),
  }),
});
