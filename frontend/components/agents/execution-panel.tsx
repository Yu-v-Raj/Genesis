"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  LoaderCircle,
  Play,
  XCircle,
} from "lucide-react";

import type { Execution, ExecutionStatus } from "@/types/executions";
import type { RealtimeEvent } from "@/types/realtime";

const lifecycle: ExecutionStatus[] = ["queued", "starting", "running", "completed"];
const terminalStatuses = new Set<ExecutionStatus>(["completed", "failed", "cancelled"]);

const statusClasses: Record<ExecutionStatus, string> = {
  pending: "border-slate-400/25 bg-slate-400/10 text-slate-200",
  queued: "border-blue-400/25 bg-blue-400/10 text-blue-200",
  starting: "border-indigo-400/25 bg-indigo-400/10 text-indigo-200",
  running: "border-amber-400/25 bg-amber-400/10 text-amber-200",
  completed: "border-emerald-400/25 bg-emerald-400/10 text-emerald-200",
  failed: "border-red-400/25 bg-red-400/10 text-red-200",
  cancelled: "border-slate-400/25 bg-slate-400/10 text-slate-300",
};

export function executionStatusClass(status: ExecutionStatus): string {
  return statusClasses[status];
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function formatTime(value: string | null): string {
  if (value === null) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function eventTime(events: RealtimeEvent[], executionId: string, status: ExecutionStatus): string | null {
  const event = events.find(
    (item) => item.payload.execution_id === executionId && item.event_type === `execution.${status}`
  );
  return event?.timestamp ?? null;
}

function currentDuration(execution: Execution, now: number): number | null {
  if (execution.duration !== null) return execution.duration;
  if (execution.started_at === null || terminalStatuses.has(execution.status)) return null;
  return Math.max(0, (now - new Date(execution.started_at).getTime()) / 1_000);
}

interface ExecutionPanelProps {
  agentName: string;
  executions: Execution[];
  events: RealtimeEvent[];
}

/** Expandable history, lifecycle, metadata, and terminal result viewer for an Agent. */
export function ExecutionPanel({ agentName, executions, events }: ExecutionPanelProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = useMemo(
    () => executions.find((execution) => execution.execution_id === selectedId) ?? executions[0] ?? null,
    [executions, selectedId]
  );

  useEffect(() => {
    if (selectedId !== null && !executions.some((execution) => execution.execution_id === selectedId)) {
      setSelectedId(null);
    }
  }, [executions, selectedId]);

  if (executions.length === 0) {
    return <p className="rounded-lg border border-dashed border-border px-4 py-5 text-sm text-muted-foreground">No executions have been recorded for this agent.</p>;
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <section>
        <h3 className="text-sm font-semibold text-foreground">Execution History</h3>
        <div className="mt-3 space-y-2">
          {executions.map((execution, index) => (
            <button
              key={execution.execution_id}
              type="button"
              onClick={() => setSelectedId(execution.execution_id)}
              className={`w-full rounded-lg border p-3 text-left transition-colors ${selected?.execution_id === execution.execution_id ? "border-primary/45 bg-primary/10" : "border-border bg-white/[0.02] hover:bg-white/[0.05]"}`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-foreground">Execution #{executions.length - index}</span>
                <ExecutionBadge status={execution.status} />
              </div>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span title={formatTime(execution.started_at)}>Started {formatTime(execution.started_at)}</span>
                <span>Duration {formatDuration(execution.duration)}</span>
                <span className="truncate">Agent {agentName}</span>
                <span className="truncate font-mono text-foreground/55">{execution.execution_id.slice(0, 8)}</span>
              </div>
            </button>
          ))}
        </div>
      </section>
      {selected !== null && <ExecutionDetail execution={selected} events={events} />}
    </div>
  );
}

export function ExecutionBadge({ status }: { status: ExecutionStatus }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-medium capitalize ${executionStatusClass(status)}`}>
    {status === "running" && <span className="h-1.5 w-1.5 animate-soft-pulse rounded-full bg-current" />}
    {status}
  </span>;
}

function ExecutionDetail({ execution, events }: { execution: Execution; events: RealtimeEvent[] }) {
  const [now, setNow] = useState(() => Date.now());
  const active = !terminalStatuses.has(execution.status);
  useEffect(() => {
    if (!active) return;
    const interval = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(interval);
  }, [active]);
  const duration = currentDuration(execution, now);
  const states: ExecutionStatus[] = execution.status === "failed" ? [...lifecycle.slice(0, 3), "failed"] : execution.status === "cancelled" ? [...lifecycle.slice(0, 3), "cancelled"] : lifecycle;

  return <section className="rounded-xl border border-border bg-white/[0.02] p-4 sm:p-5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><h3 className="text-sm font-semibold text-foreground">Execution Result</h3><p className="mt-1 text-xs text-muted-foreground">{execution.execution_id}</p></div>
      <ExecutionBadge status={execution.status} />
    </div>
    <ol className="mt-5 grid gap-2 sm:grid-cols-4">
      {states.map((state, index) => <TimelineStep key={state} state={state} current={execution.status} timestamp={eventTime(events, execution.execution_id, state) ?? (state === "running" ? execution.started_at : state === "completed" || state === "failed" || state === "cancelled" ? execution.finished_at : execution.created_at)} connector={index < states.length - 1} />)}
    </ol>
    <div className="mt-5 grid gap-4 text-xs sm:grid-cols-2">
      <Detail label="Started" value={formatTime(execution.started_at)} />
      <Detail label="Finished" value={formatTime(execution.finished_at)} />
      <Detail label="Duration" value={formatDuration(duration)} />
      <Detail label="Execution ID" value={execution.execution_id} mono />
    </div>
    <AnimatePresence mode="wait">
      <motion.div key={execution.execution_id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18 }} className="mt-5 space-y-4 border-t border-border pt-4">
        {execution.result?.output && <Detail label="Output" value={execution.result.output} prominent />}
        {execution.error && <Detail label="Error" value={execution.error} error />}
        <Detail label="Execution Metadata" value={formatJson(execution.metadata)} mono />
        {execution.result && <Detail label="Result Metadata" value={formatJson(execution.result.metadata)} mono />}
        {execution.result?.logs.length ? <Detail label="Logs" value={execution.result.logs.join("\n")} mono /> : null}
      </motion.div>
    </AnimatePresence>
  </section>;
}

function TimelineStep({ state, current, timestamp, connector }: { state: ExecutionStatus; current: ExecutionStatus; timestamp: string | null; connector: boolean }) {
  const reached = lifecycle.indexOf(state) <= lifecycle.indexOf(current) || state === current;
  const Icon = state === "completed" ? CheckCircle2 : state === "failed" ? XCircle : state === "cancelled" ? CircleAlert : state === "running" ? Play : state === "starting" ? LoaderCircle : Clock3;
  return <li className="relative flex items-start gap-2 sm:flex-col sm:gap-1"><span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${reached ? "border-primary/35 bg-primary/15 text-primary" : "border-border bg-surface text-muted-foreground"}`}><Icon className={`h-3.5 w-3.5 ${state === "running" && current === "running" ? "animate-spin" : ""}`} /></span>{connector && <span className={`absolute left-6 top-3 h-px w-4 sm:left-3 sm:top-6 sm:h-4 sm:w-px ${reached ? "bg-primary/45" : "bg-border"}`} />}<div><p className="text-xs font-medium capitalize text-foreground">{state}</p><time className="block text-[11px] text-muted-foreground">{timestamp ? formatTime(timestamp) : "Waiting"}</time></div></li>;
}

function Detail({ label, value, mono = false, prominent = false, error = false }: { label: string; value: string; mono?: boolean; prominent?: boolean; error?: boolean }) {
  return <div><dt className="text-foreground/60">{label}</dt><dd className={`mt-1 whitespace-pre-wrap break-words ${prominent ? "rounded-md border border-emerald-400/15 bg-emerald-400/5 p-3 text-sm text-emerald-100" : error ? "text-red-300" : "text-foreground/85"} ${mono ? "font-mono text-[11px]" : ""}`}>{value}</dd></div>;
}

function formatJson(value: Record<string, unknown>): string {
  return Object.keys(value).length === 0 ? "No metadata" : JSON.stringify(value, null, 2);
}
