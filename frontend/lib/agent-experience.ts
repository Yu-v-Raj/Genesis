/**
 * Pure view logic for the Agent workspace: readiness, conversation turns, and
 * user-facing error explanations. Kept free of React and browser APIs so it can be
 * unit tested with `node --test`.
 */
import type { Agent, AgentSessionSummary, LLMModelOption, LLMModelRef, SessionMessage } from "@/types/agents";

export type ReadinessState =
  | "ready"
  | "working"
  | "needs-model"
  | "model-unavailable"
  | "provider-unconfigured"
  | "not-initialized"
  | "stopped"
  | "unavailable";

export interface AgentReadiness {
  state: ReadinessState;
  label: string;
  detail: string;
  canChat: boolean;
}

export function modelKey(model: LLMModelRef): string {
  return `${model.provider}:${model.model_name}`;
}

const PROVIDER_LABELS: Record<string, string> = { gemini: "Gemini", openai: "OpenAI" };

export function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider.charAt(0).toUpperCase() + provider.slice(1);
}

export function modelLabel(model: LLMModelRef): string {
  return `${providerLabel(model.provider)} · ${model.model_name}`;
}

/** Whether the backend reports credentials for this model's provider. */
export function isModelConfigured(model: LLMModelOption): boolean {
  return model.metadata.configured === true;
}

/**
 * Explain whether an Agent can chat right now and, if not, what the user should do.
 * `models` is null while the model list is still loading.
 */
export function agentReadiness(agent: Agent, models: LLMModelOption[] | null): AgentReadiness {
  switch (agent.status) {
    case "stopped":
      return { state: "stopped", label: "Stopped", detail: "This Agent has been stopped and can no longer chat.", canChat: false };
    case "running":
      return { state: "working", label: "Working", detail: "Responding to a message…", canChat: false };
    case "created":
    case "initializing":
      return { state: "not-initialized", label: "Not ready", detail: "Finish setting up this Agent before chatting.", canChat: false };
    case "idle":
      break;
    default:
      return { state: "unavailable", label: "Unavailable", detail: `This Agent can't chat while it is ${agent.status}.`, canChat: false };
  }
  if (agent.llm_model === null) {
    return { state: "needs-model", label: "Needs a model", detail: "Choose a model in this Agent's settings before chatting.", canChat: false };
  }
  if (models !== null) {
    const selected = models.find((model) => modelKey(model) === modelKey(agent.llm_model as LLMModelRef));
    if (selected === undefined) {
      return {
        state: "model-unavailable",
        label: "Model unavailable",
        detail: `${modelLabel(agent.llm_model)} is not offered by this Genesis server. Choose another model.`,
        canChat: false,
      };
    }
    if (!isModelConfigured(selected)) {
      return {
        state: "provider-unconfigured",
        label: "Provider not configured",
        detail: `The Genesis server has no API key for ${providerLabel(selected.provider)}. Add it to the backend .env file and restart the backend.`,
        // Chat stays possible so the backend can report the precise credential error.
        canChat: true,
      };
    }
  }
  return { state: "ready", label: "Ready", detail: "Ready to chat.", canChat: true };
}

export interface ToolStep {
  name: string;
  status: "completed" | "failed" | "rejected" | string;
  result: unknown;
  error: string | null;
}

export interface ConversationTurn {
  id: string;
  user: string | null;
  tools: ToolStep[];
  reply: string | null;
}

/** Parse the JSON envelope Genesis sends back to the LLM for each tool call. */
export function parseToolContent(content: string): { result: unknown; error: string | null } {
  try {
    const parsed: unknown = JSON.parse(content);
    if (typeof parsed === "object" && parsed !== null) {
      const record = parsed as Record<string, unknown>;
      return {
        result: "result" in record ? record.result : null,
        error: typeof record.error === "string" ? record.error : null,
      };
    }
  } catch {
    // Older or non-JSON tool messages are shown as plain results.
  }
  return { result: content, error: null };
}

/** Group a flat session into user turns, each with its tool steps and final reply. */
export function groupTurns(messages: SessionMessage[]): ConversationTurn[] {
  const turns: ConversationTurn[] = [];
  const byInteraction = new Map<string, ConversationTurn>();
  messages.forEach((message, index) => {
    // Messages without an interaction id belong to the turn opened by the last user message.
    let turn =
      message.interaction_id !== null
        ? byInteraction.get(message.interaction_id)
        : message.role === "user"
          ? undefined
          : turns.at(-1);
    if (turn === undefined) {
      turn = { id: message.interaction_id ?? `message-${index}`, user: null, tools: [], reply: null };
      if (message.interaction_id !== null) byInteraction.set(message.interaction_id, turn);
      turns.push(turn);
    }
    if (message.role === "user") {
      turn.user = message.content;
    } else if (message.role === "tool") {
      const { result, error } = parseToolContent(message.content);
      turn.tools.push({ name: message.tool_name ?? "tool", status: message.tool_status ?? (error ? "failed" : "completed"), result, error });
    } else if (message.content.trim()) {
      turn.reply = message.content;
    }
  });
  return turns;
}

const REJECTION_TEXT: Record<string, string> = {
  "Requested tool is not allowed.": "Not allowed for this Agent",
  "Requested tool is unavailable.": "Tool is not available",
  "Tool arguments are invalid.": "The request to this tool was invalid",
};

export function toolStepLabel(step: ToolStep): string {
  if (step.status === "completed") return "Completed";
  if (step.status === "rejected") return `Blocked — ${REJECTION_TEXT[step.error ?? ""] ?? "not permitted"}`;
  return "Couldn't complete";
}

export function formatToolValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

export interface ChatProblem {
  title: string;
  message: string;
  /** Suggests opening the Agent's settings to fix the problem. */
  configure: boolean;
}

/** Translate a failed chat request into something a user can act on. */
export function describeChatError(status: number | undefined, detail: string): ChatProblem {
  if (status === undefined) {
    return { title: "Can't reach Genesis", message: "The backend isn't responding. Check that it is running, then try again.", configure: false };
  }
  switch (status) {
    case 503:
      return { title: "The model isn't available", message: detail, configure: true };
    case 409:
      return { title: "The Agent can't take this message", message: detail, configure: false };
    case 404:
      return { title: "Not found", message: detail, configure: true };
    case 504:
      return { title: "The model took too long", message: "The provider didn't answer in time. Try again.", configure: false };
    case 502:
      return { title: "The model provider returned an error", message: `${detail} Try again in a moment.`, configure: false };
    case 422:
      return { title: "The request was rejected", message: detail, configure: false };
    default:
      return { title: "Something went wrong", message: detail, configure: false };
  }
}

/** A short, human label for a stored conversation in a picker. */
export function sessionLabel(session: AgentSessionSummary, now: Date = new Date()): string {
  const title = session.title ?? (session.message_count === 0 ? "New conversation" : "Conversation");
  return `${title} · ${relativeDay(new Date(session.updated_at), now)}`;
}

function relativeDay(date: Date, now: Date): string {
  if (Number.isNaN(date.getTime())) return "unknown date";
  const startOfDay = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (days <= 0) return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return date.toLocaleDateString();
}
