"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronRight, Radio } from "lucide-react";

import { EVENT_ICONS } from "@/components/operations/event-stream";
import { Button } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { JsonView } from "@/components/ui/disclosure";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { describeEvent, eventCategory } from "@/lib/activity";
import { relativeTime } from "@/lib/operations";
import { DURABLE_EVENT_FILTERS, asRealtimeEvent, eventFilterType, mergeEvents } from "@/lib/traces";
import { cn } from "@/lib/utils";
import { OperationsApiError, OperationsService } from "@/services/operations.service";
import type { RuntimeEvent } from "@/types/operations";

const PAGE = 100;

function Row({ event, agentNames, now }: { event: RuntimeEvent; agentNames: Record<string, string>; now: Date }) {
  const [open, setOpen] = useState(false);
  const live = asRealtimeEvent(event);
  const Icon = EVENT_ICONS[eventCategory(event.event_type)];
  const candidates: [string, string | null][] = [
    ["Execution", event.execution_id ?? event.interaction_id], ["Workflow run", event.workflow_id], ["Step", event.step_id],
    ["Tool run", event.tool_task_id], ["Approval", event.approval_id],
  ];
  const links = candidates.filter((item): item is [string, string] => typeof item[1] === "string");
  return (
    <li>
      <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)} className="flex w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-white/[0.025]">
        <Icon aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1">
          <span className="block break-words text-xs text-foreground">{describeEvent(live, agentNames)}</span>
          <span className="mt-0.5 block font-mono text-[11px] text-muted-foreground">{event.event_type}</span>
        </span>
        <time dateTime={event.occurred_at} title={new Date(event.occurred_at).toLocaleString()} className="shrink-0 text-[11px] text-muted-foreground">{relativeTime(event.occurred_at, now)}</time>
        <ChevronRight aria-hidden className={cn("mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-150", open && "rotate-90")} />
      </button>
      {open && (
        <div className="flex flex-col gap-2 px-4 pb-3 pl-10">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span>Source: <span className="text-foreground/90">{event.source}</span></span>
            <span aria-hidden>·</span>
            <span>#{event.sequence}</span>
            <CopyButton value={JSON.stringify(event, null, 2)} label="Copy event JSON" />
          </div>
          {links.length > 0 && (
            <dl className="grid grid-cols-1 gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-2">
              {links.map(([label, value]) => (
                <div key={label} className="flex min-w-0 gap-1.5"><dt className="shrink-0 text-muted-foreground">{label}</dt><dd className="truncate font-mono text-foreground/90">{value}</dd></div>
              ))}
            </dl>
          )}
          <JsonView value={event.payload} />
        </div>
      )}
    </li>
  );
}

/**
 * Lifecycle events stored in the database (runs, workflow steps, tool runs, approvals,
 * model calls), newest first, paging back in time. Kept across restarts for the
 * configured retention period; heartbeats and log lines are not stored.
 */
export function DurableEvents({ agentNames, now, refreshKey }: { agentNames: Record<string, string>; now: Date; refreshKey: string | null }) {
  const [filter, setFilter] = useState("all");
  const [state, setState] = useState<{ filter: string; events: RuntimeEvent[]; nextBefore: number | null } | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadNewest = useCallback(async (value: string) => {
    try {
      const page = await OperationsService.events({ limit: PAGE, event_type: eventFilterType(value) });
      setState((current) => current && current.filter === value
        ? { ...current, events: mergeEvents(current.events, page.events) }
        : { filter: value, events: page.events, nextBefore: page.next_before_sequence });
      setError(null);
    } catch (cause) {
      setError(cause instanceof OperationsApiError ? cause.message : "Stored events couldn't be loaded.");
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void loadNewest(filter)); }, [loadNewest, filter]);
  // A live lifecycle event arrived: fetch the newest page once the recorder has stored it
  // (it writes in the background, about every half second).
  useEffect(() => {
    if (refreshKey === null) return;
    const timer = setTimeout(() => void loadNewest(filter), 1_000);
    return () => clearTimeout(timer);
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadOlder() {
    if (!state?.nextBefore) return;
    setLoadingOlder(true);
    try {
      const page = await OperationsService.events({ limit: PAGE, event_type: eventFilterType(state.filter), before_sequence: state.nextBefore });
      setState((current) => current && current.filter === state.filter ? { ...current, events: mergeEvents(current.events, page.events), nextBefore: page.next_before_sequence } : current);
    } catch (cause) {
      setError(cause instanceof OperationsApiError ? cause.message : "Older events couldn't be loaded.");
    } finally {
      setLoadingOlder(false);
    }
  }

  const events = state?.filter === filter ? state.events : null;

  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label="Stored event type" className="flex flex-wrap gap-1">
        {DURABLE_EVENT_FILTERS.map((item) => (
          <button key={item.value} type="button" aria-pressed={filter === item.value} onClick={() => setFilter(item.value)}
            className={cn("h-8 rounded-md px-2.5 text-xs font-medium transition-colors", filter === item.value ? "bg-white/[0.08] text-foreground" : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground")}>
            {item.label}
          </button>
        ))}
      </div>
      {error && <Alert tone={events === null ? "danger" : "warning"} action={<Button size="sm" onClick={() => void loadNewest(filter)}>Try again</Button>}>{error}</Alert>}
      {events === null ? (
        !error && <div className="flex flex-col gap-2" aria-busy="true">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-10 w-full" />)}</div>
      ) : events.length === 0 ? (
        <EmptyState icon={Radio} title="No stored events" description={filter === "all" ? "Run, workflow, tool, approval and model-call events are stored here as they happen." : "Nothing of this type has been recorded yet."} />
      ) : (
        <div className="rounded-lg border border-border bg-surface">
          <ul aria-label="Stored events" className="max-h-[32rem] divide-y divide-border overflow-y-auto">
            {events.map((event) => <Row key={event.sequence} event={event} agentNames={agentNames} now={now} />)}
          </ul>
          {state?.nextBefore ? (
            <button type="button" onClick={() => void loadOlder()} disabled={loadingOlder} className="w-full border-t border-border py-2 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-60">
              {loadingOlder ? "Loading…" : "Load older events"}
            </button>
          ) : (
            <p className="border-t border-border py-2 text-center text-[11px] text-subtle">That&apos;s everything kept for this view.</p>
          )}
        </div>
      )}
    </div>
  );
}
