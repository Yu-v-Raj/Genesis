import type {
  Agent,
  AgentContext,
  AgentListResponse,
  CreateAgentInput,
} from "@/types/agents";

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
  let response: Response;
  try {
    response = await fetch(`${AGENT_API_BASE_URL}${endpoint}`, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch {
    throw new AgentApiError("Unable to connect to the Genesis Agent Runtime API.");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status} ${response.statusText}).`;
    try {
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Keep the stable fallback message when the error response is not JSON.
    }
    throw new AgentApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
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
