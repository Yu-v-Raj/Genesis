import type {
  HealthApiResponse,
  RuntimeApiResponse,
  ServicesApiResponse,
  ToolsApiResponse,
  PluginsApiResponse,
  MemoryApiResponse,
  WorkflowsApiResponse,
} from "@/types/system";

/**
 * Base URL of the Genesis System API.
 *
 * Configure this in:
 * frontend/.env.local
 *
 * Example:
 * NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000/api/system
 */
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/system";

/**
 * Typed error used throughout the frontend whenever
 * communication with the Genesis backend fails.
 */
export class SystemApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "SystemApiError";
    this.status = status;
  }
}

/**
 * Generic GET request helper.
 * Every System API request flows through this function.
 */
async function request<T>(endpoint: string): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch {
    throw new SystemApiError(
      `Unable to connect to the Genesis backend (${endpoint}). Please verify that the backend is running.`
    );
  }

  if (!response.ok) {
    throw new SystemApiError(
      `Request to "${endpoint}" failed (${response.status} ${response.statusText}).`,
      response.status
    );
  }

  try {
    return response.json();
  } catch {
    throw new SystemApiError(
      `The backend returned an invalid JSON response for "${endpoint}".`
    );
  }
}

/**
 * Centralized System API.
 *
 * React components must NEVER call fetch() directly.
 * All backend communication flows through this service.
 */
export const SystemService = Object.freeze({
  getHealth: (): Promise<HealthApiResponse> =>
    request("/health"),

  getRuntime: (): Promise<RuntimeApiResponse> =>
    request("/runtime"),

  getServices: (): Promise<ServicesApiResponse> =>
    request("/services"),

  getTools: (): Promise<ToolsApiResponse> =>
    request("/tools"),

  getPlugins: (): Promise<PluginsApiResponse> =>
    request("/plugins"),

  getMemory: (): Promise<MemoryApiResponse> =>
    request("/memory"),

  getWorkflows: (): Promise<WorkflowsApiResponse> =>
    request("/workflows"),
});
