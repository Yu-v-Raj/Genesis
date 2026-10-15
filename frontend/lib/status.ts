/**
 * One mapping from every backend status to how the UI presents it.
 *
 * Agents, executions, tools and workflows share vocabulary ("running", "failed", ...), so a
 * single table keeps their colors and wording consistent. Unknown values fall back to a
 * neutral tone with the raw value as the label, so a new backend status is never hidden.
 */

export type StatusTone = "success" | "warning" | "danger" | "info" | "running" | "neutral";

export interface StatusPresentation {
  tone: StatusTone;
  label: string;
  /** Work is in progress; the badge may show a live indicator. */
  active: boolean;
}

const STATUSES: Readonly<Record<string, StatusPresentation>> = {
  // Shared across agents, executions, tools and workflows
  running: { tone: "running", label: "Running", active: true },
  completed: { tone: "success", label: "Completed", active: false },
  failed: { tone: "danger", label: "Failed", active: false },
  cancelled: { tone: "neutral", label: "Cancelled", active: false },
  interrupted: { tone: "warning", label: "Interrupted", active: false },
  pending: { tone: "neutral", label: "Pending", active: false },
  queued: { tone: "info", label: "Queued", active: false },
  // Executions
  starting: { tone: "running", label: "Starting", active: true },
  // Agents
  created: { tone: "neutral", label: "Created", active: false },
  initializing: { tone: "running", label: "Initializing", active: true },
  idle: { tone: "success", label: "Idle", active: false },
  waiting: { tone: "info", label: "Waiting", active: false },
  paused: { tone: "warning", label: "Paused", active: false },
  stopped: { tone: "neutral", label: "Stopped", active: false },
  // Tools
  ready: { tone: "success", label: "Ready", active: false },
  disabled: { tone: "neutral", label: "Disabled", active: false },
  rejected: { tone: "danger", label: "Rejected", active: false },
  // Workflow tasks
  blocked: { tone: "warning", label: "Blocked", active: false },
  // Services and health
  healthy: { tone: "success", label: "Healthy", active: false },
  online: { tone: "success", label: "Online", active: false },
  offline: { tone: "danger", label: "Offline", active: false },
  ok: { tone: "success", label: "OK", active: false },
  degraded: { tone: "warning", label: "Degraded", active: false },
  unhealthy: { tone: "danger", label: "Unhealthy", active: false },
  // Model provider readiness (UI states; see lib/providers.ts). Configuration alone never
  // reads as verified: only a recorded successful response does.
  configured: { tone: "info", label: "Configured", active: false },
  not_configured: { tone: "neutral", label: "Not configured", active: false },
  provider_responding: { tone: "success", label: "Recent successful response", active: false },
  provider_failing: { tone: "danger", label: "Recent failure", active: false },
  unavailable: { tone: "neutral", label: "Status unavailable", active: false },
  // Realtime connection
  connected: { tone: "success", label: "Connected", active: false },
  connecting: { tone: "info", label: "Connecting", active: true },
  disconnected: { tone: "danger", label: "Disconnected", active: false },
};

function humanize(value: string): string {
  const words = value.replace(/[_-]+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "Unknown";
}

export function statusPresentation(status: string | null | undefined): StatusPresentation {
  const key = (status ?? "").trim().toLowerCase();
  return STATUSES[key] ?? { tone: "neutral", label: humanize(key), active: false };
}

export const MEMORY_KIND_TONES: Readonly<Record<string, StatusTone>> = {
  fact: "info",
  note: "neutral",
  preference: "running",
  context: "warning",
};
