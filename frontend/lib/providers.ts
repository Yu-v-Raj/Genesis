/**
 * Honest model-provider readiness.
 *
 * `configured` from `GET /api/llm/models` only means credentials are present. Whether a
 * provider actually answers is known only from recorded `llm.completed` / `llm.failed`
 * events, which the backend keeps in memory since it last started. A provider is never
 * shown as working on configuration alone.
 */
import type { LLMModelOption } from "@/types/agents";
import type { RealtimeEvent } from "@/types/realtime";
import { providerLabel } from "./agent-experience.ts";

export type ProviderState = "provider_responding" | "provider_failing" | "configured" | "not_configured";

export type ProviderEvidence =
  | { kind: "success"; at: string; model: string | null }
  | { kind: "failure"; at: string; model: string | null; reason: string }
  | { kind: "none" };

export interface ProviderReadiness {
  provider: string;
  label: string;
  models: string[];
  configured: boolean;
  /** A key into lib/status.ts. */
  state: ProviderState;
  evidence: ProviderEvidence;
}

/** Only exception class names known to be safe are translated; anything else stays generic. */
const FAILURE_REASONS: Readonly<Record<string, string>> = {
  LLMConfigurationError: "The provider rejected the request configuration, for example the API key.",
  LLMTimeoutError: "The provider did not respond in time.",
  ProviderUnavailableError: "The provider is unavailable.",
  LLMProviderError: "The provider returned an error.",
};

function failureReason(errorType: unknown): string {
  return typeof errorType === "string" && FAILURE_REASONS[errorType] ? FAILURE_REASONS[errorType] : "The request failed.";
}

function latestOutcome(provider: string, events: readonly RealtimeEvent[]): ProviderEvidence {
  let latest: RealtimeEvent | null = null;
  for (const event of events) {
    if (event.event_type !== "llm.completed" && event.event_type !== "llm.failed") continue;
    if (event.payload.provider !== provider) continue;
    if (latest === null || Date.parse(event.timestamp) > Date.parse(latest.timestamp)) latest = event;
  }
  if (latest === null) return { kind: "none" };
  const model = typeof latest.payload.model === "string" ? latest.payload.model : null;
  return latest.event_type === "llm.completed"
    ? { kind: "success", at: latest.timestamp, model }
    : { kind: "failure", at: latest.timestamp, model, reason: failureReason(latest.payload.error_type) };
}

export function providerReadiness(models: readonly LLMModelOption[], events: readonly RealtimeEvent[]): ProviderReadiness[] {
  const byProvider = new Map<string, LLMModelOption[]>();
  for (const model of models) byProvider.set(model.provider, [...(byProvider.get(model.provider) ?? []), model]);

  return [...byProvider.entries()].map(([provider, options]) => {
    const configured = options.some((option) => option.metadata?.configured === true);
    const evidence = latestOutcome(provider, events);
    const state: ProviderState = !configured
      ? "not_configured"
      : evidence.kind === "success"
        ? "provider_responding"
        : evidence.kind === "failure"
          ? "provider_failing"
          : "configured";
    return { provider, label: providerLabel(provider), models: options.map((option) => option.model_name), configured, state, evidence };
  }).sort((a, b) => Number(b.configured) - Number(a.configured) || a.label.localeCompare(b.label));
}

// ------------------------------------------------------------------ provider page

/** Agents configured to use this exact model. */
export function agentsUsingModel<T extends { llm_model: { provider: string; model_name: string } | null }>(agents: readonly T[], provider: string, modelName: string): T[] {
  return agents.filter((agent) => agent.llm_model?.provider === provider && agent.llm_model.model_name === modelName);
}

export interface ModelCall {
  id: string;
  at: string;
  model: string | null;
  ok: boolean;
  durationMs: number | null;
  totalTokens: number | null;
  /** A fixed, readable explanation for failures; never the raw provider message. */
  reason: string | null;
}

/** Recorded model calls for a provider, newest first, reduced to safe fields. */
export function modelCalls(events: readonly RealtimeEvent[], provider: string): ModelCall[] {
  return events
    .filter((event) => (event.event_type === "llm.completed" || event.event_type === "llm.failed") && event.payload.provider === provider)
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
    .map((event) => {
      const ok = event.event_type === "llm.completed";
      const duration = Number(event.payload.duration_ms);
      const usage = event.payload.usage;
      const total = usage && typeof usage === "object" && !Array.isArray(usage) ? Number((usage as Record<string, unknown>).total_tokens) : NaN;
      return {
        id: event.id,
        at: event.timestamp,
        model: typeof event.payload.model === "string" ? event.payload.model : null,
        ok,
        durationMs: Number.isFinite(duration) ? duration : null,
        totalTokens: Number.isFinite(total) ? total : null,
        reason: ok ? null : failureReason(event.payload.error_type),
      };
    });
}

/**
 * Remove anything shaped like a credential before showing server text. The backend already
 * sanitizes its errors; this is a second line of defence for display only.
 */
export function redactSecrets(text: string): string {
  return text
    .replace(/AIza[0-9A-Za-z_-]{20,}/g, "[redacted]")
    .replace(/\bAQ\.[0-9A-Za-z._-]{20,}/g, "[redacted]")
    .replace(/\bsk-[0-9A-Za-z_-]{16,}/g, "[redacted]")
    .replace(/Bearer\s+[0-9A-Za-z._~+/=-]{16,}/gi, "Bearer [redacted]")
    .replace(/([?&](?:key|api_key|token)=)[^&\s]+/gi, "$1[redacted]");
}

const TEST_FAILURES: Readonly<Record<number, string>> = {
  404: "This provider or model isn't registered on the server.",
  422: "The server rejected the test request.",
  502: "The provider returned an error.",
  503: "The provider is unavailable or its configuration was rejected.",
  504: "The provider didn't respond in time.",
};

/** A readable title for a failed test request, by HTTP status. */
export function testFailureTitle(status: number | undefined): string {
  if (status === undefined) return "Genesis couldn't reach the server.";
  return TEST_FAILURES[status] ?? "The test request failed.";
}
