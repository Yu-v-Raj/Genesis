"use client";

import { useState } from "react";
import {
  BarChart3, Bot, Brain, Check, ChevronDown, CircleStop, ClipboardList, Clock3, Code2, Cpu,
  FileText, Globe2, LoaderCircle, Pause, Play, Trash2, XCircle,
} from "lucide-react";

import type { Agent, AgentContext } from "@/types/agents";
import type { RealtimeEvent } from "@/types/realtime";

type LifecycleAction = "initialize" | "start" | "pause" | "resume" | "stop" | "delete";

interface AgentCardProps {
  agent: Agent;
  context: AgentContext | null | undefined;
  events: RealtimeEvent[];
  pending: boolean;
  onAction: (agentId: string, action: LifecycleAction) => Promise<boolean>;
  onLoadContext: (agentId: string) => Promise<void>;
}

const statusPresentation: Record<Agent["status"], { className: string; Icon: typeof Clock3 }> = {
  created: { className: "border-slate-400/25 bg-slate-400/10 text-slate-200", Icon: Clock3 },
  initializing: { className: "border-amber-400/25 bg-amber-400/10 text-amber-200", Icon: LoaderCircle },
  idle: { className: "border-blue-400/25 bg-blue-400/10 text-blue-200", Icon: Clock3 },
  running: { className: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200", Icon: Play },
  waiting: { className: "border-amber-400/25 bg-amber-400/10 text-amber-200", Icon: Clock3 },
  paused: { className: "border-orange-400/25 bg-orange-400/10 text-orange-200", Icon: Pause },
  completed: { className: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200", Icon: Check },
  failed: { className: "border-red-400/25 bg-red-400/10 text-red-200", Icon: XCircle },
  stopped: { className: "border-slate-400/25 bg-slate-400/10 text-slate-200", Icon: CircleStop },
};

function actionsFor(status: Agent["status"]): LifecycleAction[] {
  if (status === "created") return ["initialize", "stop"];
  if (status === "idle") return ["start", "stop"];
  if (status === "running") return ["pause", "stop"];
  if (status === "waiting") return ["start", "stop"];
  if (status === "paused") return ["resume", "stop"];
  if (status === "stopped") return ["delete"];
  return status === "completed" || status === "failed" ? ["stop"] : [];
}

function actionLabel(action: LifecycleAction): string {
  return action.charAt(0).toUpperCase() + action.slice(1);
}

function ActionIcon({ action }: { action: LifecycleAction }) {
  if (action === "pause") return <Pause className="h-3.5 w-3.5" />;
  if (action === "stop") return <CircleStop className="h-3.5 w-3.5" />;
  if (action === "delete") return <Trash2 className="h-3.5 w-3.5" />;
  return <Play className="h-3.5 w-3.5" />;
}

function AgentTypeIcon({ type }: { type: string }) {
  const normalized = type.toLowerCase();
  const Icon = normalized.includes("research") ? Brain
    : normalized.includes("code") || normalized.includes("develop") ? Code2
      : normalized.includes("system") ? Cpu
        : normalized.includes("analytic") || normalized.includes("data") ? BarChart3
          : normalized.includes("doc") || normalized.includes("write") ? FileText
            : normalized.includes("web") ? Globe2
              : normalized.includes("plan") ? ClipboardList : Bot;
  return <Icon className="h-4 w-4" aria-hidden="true" />;
}

export function AgentCard({ agent, context, events, pending, onAction, onLoadContext }: AgentCardProps) {
  const [expanded, setExpanded] = useState(false);
  const agentEvents = events.filter((event) => event.payload.agent_id === agent.id);
  const status = statusPresentation[agent.status];
  const StatusIcon = status.Icon;

  async function toggleContext() {
    const nextExpanded = !expanded;
    setExpanded(nextExpanded);
    if (nextExpanded && context === undefined) await onLoadContext(agent.id);
  }

  return (
    <article className="rounded-xl border border-border bg-surface p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-white/15 hover:shadow-lg hover:shadow-black/15 sm:p-6">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/15 bg-primary/10 text-primary"><AgentTypeIcon type={agent.type} /></span>
            <h2 className="text-base font-semibold tracking-tight text-foreground">{agent.name}</h2>
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs font-medium capitalize ${status.className}`}>
              {agent.status === "running" && <span className="h-1.5 w-1.5 rounded-full bg-current animate-soft-pulse" />}
              <StatusIcon className={`h-3 w-3 ${agent.status === "initializing" ? "animate-spin" : ""}`} />
              {agent.status}
            </span>
          </div>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">{agent.description}</p>
          <dl className="mt-4 grid gap-x-8 gap-y-2 text-xs text-muted-foreground sm:grid-cols-3">
            <div><dt className="inline text-foreground/70">Type: </dt><dd className="inline capitalize">{agent.type}</dd></div>
            <div><dt className="inline text-foreground/70">Created: </dt><dd className="inline" title={formatFullDate(agent.created_at)}>{formatRelativeTime(agent.created_at)}</dd></div>
            <div><dt className="inline text-foreground/70">Updated: </dt><dd className="inline" title={formatFullDate(agent.updated_at)}>{formatRelativeTime(agent.updated_at)}</dd></div>
          </dl>
          {agent.tags.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {agent.tags.map((tag) => <span key={tag} className="rounded-md border border-white/[0.06] bg-white/[0.04] px-2 py-1 text-xs text-muted-foreground">{tag}</span>)}
            </div>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          {actionsFor(agent.status).map((action) => (
            <button key={action} type="button" onClick={() => void onAction(agent.id, action)} disabled={pending} className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-all active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${action === "delete" ? "border-red-400/20 text-red-200 hover:bg-red-400/10" : "border-border text-foreground hover:bg-white/[0.06]"}`}>
              {pending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <ActionIcon action={action} />}
              {pending ? "Working..." : actionLabel(action)}
            </button>
          ))}
        </div>
      </div>

      <button type="button" onClick={() => void toggleContext()} className="mt-6 inline-flex items-center gap-1.5 border-t border-transparent pt-1 text-xs font-medium text-primary transition-colors hover:text-primary/80" aria-expanded={expanded}>
        Runtime context & timeline <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>

      {expanded && <div className="mt-4 grid gap-6 border-t border-border pt-5 lg:grid-cols-2"><ContextPanel context={context} /><Timeline events={agentEvents} /></div>}
    </article>
  );
}

function ContextPanel({ context }: { context: AgentContext | null | undefined }) {
  if (context === undefined) return <p className="text-sm text-muted-foreground">Loading runtime context...</p>;
  if (context === null) return <EmptyPanel text="No runtime context is available for this agent." />;
  return <section><h3 className="text-sm font-semibold text-foreground">Runtime Context</h3><dl className="mt-3 grid gap-3 text-xs text-muted-foreground">
    <div><dt className="text-foreground/70">Session ID</dt><dd className="mt-1 break-all font-mono">{context.session_id}</dd></div>
    <div><dt className="text-foreground/70">Current state</dt><dd className="mt-1 capitalize">{context.current_state}</dd></div>
    <div><dt className="text-foreground/70">Current task</dt><dd className="mt-1">{context.current_task || "No active task"}</dd></div>
    <div><dt className="text-foreground/70">Runtime metadata</dt><dd className="mt-1"><JsonValue value={context.runtime_metadata} emptyText="No runtime metadata yet" /></dd></div>
    <div><dt className="text-foreground/70">Temporary variables</dt><dd className="mt-1"><JsonValue value={context.temporary_variables} emptyText="Temporary variables will appear during execution" /></dd></div>
  </dl></section>;
}

function EmptyPanel({ text }: { text: string }) { return <p className="rounded-lg border border-dashed border-border px-4 py-5 text-sm text-muted-foreground">{text}</p>; }

function Timeline({ events }: { events: RealtimeEvent[] }) {
  return <section><h3 className="text-sm font-semibold text-foreground">Lifecycle Timeline</h3>{events.length === 0 ? <EmptyPanel text="No lifecycle events have been recorded yet." /> : <ol className="mt-4 space-y-4 border-l border-border pl-5">
    {[...events].reverse().map((event) => { const Icon = event.event_type.includes("failed") ? XCircle : event.event_type.includes("stop") ? CircleStop : event.event_type.includes("pause") ? Pause : event.event_type.includes("start") || event.event_type.includes("resume") ? Play : Clock3; return <li key={event.id} className="relative"><span className="absolute -left-[1.8rem] top-0 flex h-5 w-5 items-center justify-center rounded-full border border-primary/20 bg-surface text-primary"><Icon className="h-3 w-3" /></span><p className="text-xs font-medium capitalize text-foreground">{event.event_type.replace("agent.", "")}</p><time className="mt-0.5 block text-xs text-muted-foreground" title={formatFullDate(event.timestamp)}>{formatRelativeTime(event.timestamp)}</time></li>; })}
  </ol>}</section>;
}

function JsonValue({ value, emptyText }: { value: Record<string, unknown>; emptyText: string }) { return Object.keys(value).length === 0 ? emptyText : <code className="break-all text-foreground/80">{JSON.stringify(value)}</code>; }

function formatRelativeTime(value: string): string { const date = new Date(value); const seconds = Math.round((date.getTime() - Date.now()) / 1000); if (Number.isNaN(date.getTime())) return value; const absolute = Math.abs(seconds); if (absolute < 45) return "Just now"; const units: [number, Intl.RelativeTimeFormatUnit][] = [[60, "second"], [60, "minute"], [24, "hour"], [7, "day"], [4.34524, "week"], [12, "month"], [Number.POSITIVE_INFINITY, "year"]]; let duration = absolute; for (const [amount, unit] of units) { if (duration < amount) return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(Math.round(seconds / (absolute / duration)), unit); duration /= amount; } return value; }
function formatFullDate(value: string): string { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }
