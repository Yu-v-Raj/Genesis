import { requestJson } from "@/services/api-client";
import type {
  CreateMemoryInput,
  MemoryListResponse,
  MemoryRecord,
  UpdateMemoryInput,
} from "@/types/memory";

const MEMORY_API_BASE_URL =
  process.env.NEXT_PUBLIC_MEMORY_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export class MemoryApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "MemoryApiError";
    this.status = status;
  }
}

function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  return requestJson(
    MEMORY_API_BASE_URL,
    endpoint,
    init,
    "Unable to connect to the Genesis Memory Runtime API.",
    (message, status) => new MemoryApiError(message, status)
  );
}

const json = (method: "POST" | "PATCH", body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Typed transport adapter for the Memory Runtime REST API. */
export const MemoryService = Object.freeze({
  list: (): Promise<MemoryListResponse> => request<MemoryListResponse>("/memory"),
  get: (memoryId: string): Promise<MemoryRecord> => request<MemoryRecord>(`/memory/${memoryId}`),
  update: (memoryId: string, input: UpdateMemoryInput): Promise<MemoryRecord> =>
    request<MemoryRecord>(`/memory/${memoryId}`, json("PATCH", input)),
  delete: (memoryId: string): Promise<MemoryRecord> =>
    request<MemoryRecord>(`/memory/${memoryId}`, { method: "DELETE" }),
  listForAgent: (agentId: string): Promise<MemoryListResponse> =>
    request<MemoryListResponse>(`/agents/${agentId}/memory`),
  create: (agentId: string, input: CreateMemoryInput): Promise<MemoryRecord> =>
    request<MemoryRecord>(`/agents/${agentId}/memory`, json("POST", input)),
  search: (agentId: string, query: string): Promise<MemoryListResponse> =>
    request<MemoryListResponse>(`/agents/${agentId}/memory/search?query=${encodeURIComponent(query)}`),
});
