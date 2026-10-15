import { requestJson } from "@/services/api-client";
import type { LLMModelOption } from "@/types/agents";

const LLM_API_BASE_URL = process.env.NEXT_PUBLIC_LLM_API_BASE_URL ?? "http://127.0.0.1:8000/api/llm";

export class LlmApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "LlmApiError";
    this.status = status;
  }
}

function request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
  return requestJson(LLM_API_BASE_URL, endpoint, init, "Unable to connect to the Genesis LLM Runtime API.", (message, status) => new LlmApiError(message, status));
}

export interface GenerateResult {
  content: string | null;
  model: LLMModelOption;
  finish_reason: string | null;
  usage: { input_tokens: number; output_tokens: number; total_tokens: number };
}

/**
 * Typed adapter for the LLM Runtime's existing endpoints. Credentials never pass through
 * here: the server holds them, and responses only say whether a provider is configured.
 */
export const LlmService = Object.freeze({
  providers: (): Promise<{ providers: string[] }> => request("/providers"),
  models: (): Promise<{ models: LLMModelOption[] }> => request("/models"),
  /**
   * One real request through the server (the endpoint exists for integration checks).
   * Only ever called from an explicit user action.
   */
  testModel: (model: { provider: string; model_name: string }): Promise<GenerateResult> =>
    request("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content: "Reply with the single word OK." }],
        generation: { max_tokens: 32 },
      }),
    }),
});
