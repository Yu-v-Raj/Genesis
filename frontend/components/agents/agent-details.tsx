"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, FlaskConical, Square } from "lucide-react";

import { Button, buttonClasses } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Dialog } from "@/components/ui/dialog";
import { JsonView } from "@/components/ui/disclosure";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { StatusBadge } from "@/components/ui/status-badge";
import { Tabs, tabPanelProps, type TabItem } from "@/components/ui/tabs";
import { describeEvent } from "@/lib/activity";
import { modelLabel } from "@/lib/agent-experience";
import { executionLabel, isActive } from "@/lib/durable-work";
import { formatDuration, operationsQuery, relativeTime } from "@/lib/operations";
import type { Agent, AgentContext } from "@/types/agents";
import type { Execution } from "@/types/executions";
import type { RealtimeEvent } from "@/types/realtime";

type Tab = "overview" | "runs" | "runtime" | "lifecycle";
const TAB_PREFIX = "agent-details";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-xs text-foreground">{children}</dd>
    </div>
  );
}

/**
 * Everything an engineer may want about one Agent, kept out of the conversation: its
 * configuration, its runs (with the test-run and cancel controls), runtime context and
 * lifecycle events.
 */
export function AgentDetails({ agent, open, onClose, executions, events, context, onLoadContext, onTestRun, testRunPending, onCancelRun, cancellingIds, error }: {
  agent: Agent;
  open: boolean;
  onClose: () => void;
  executions: Execution[];
  events: RealtimeEvent[];
  context: AgentContext | null | undefined;
  onLoadContext: () => void;
  onTestRun: () => void;
  testRunPending: boolean;
  onCancelRun: (executionId: string) => void;
  cancellingIds: ReadonlySet<string>;
  error: string | null;
}) {
  const [tab, setTab] = useState<Tab>("overview");
  const now = new Date();
  const agentEvents = events.filter((event) => event.payload.agent_id === agent.id);
  const activeRun = executions.find((execution) => isActive(execution.status));

  useEffect(() => {
    if (open && tab === "runtime" && context === undefined) onLoadContext();
  }, [open, tab, context, onLoadContext]);

  const tabs: TabItem<Tab>[] = [
    { value: "overview", label: "Overview" },
    { value: "runs", label: "Runs", badge: executions.length },
    { value: "runtime", label: "Runtime" },
    { value: "lifecycle", label: "Lifecycle" },
  ];

  return (
    <Dialog open={open} onClose={onClose} variant="sheet" title={agent.name} description="Agent details">
      <Tabs idPrefix={TAB_PREFIX} label="Agent details" items={tabs} value={tab} onChange={setTab} className="-mx-4 px-2" />
      <div {...tabPanelProps(TAB_PREFIX, tab)} className="pt-4 focus:outline-none">
        {error && <Alert tone="danger" className="mb-3">{error}</Alert>}

        {tab === "overview" && (
          <dl className="divide-y divide-border">
            <Row label="Status"><StatusBadge status={agent.status} /></Row>
            <Row label="Description">{agent.description || "—"}</Row>
            <Row label="Model">{agent.llm_model ? modelLabel(agent.llm_model) : "No model selected"}</Row>
            <Row label="Tools">{agent.allowed_tools.length ? agent.allowed_tools.map((tool) => tool.replaceAll("_", " ")).join(", ") : "None"}</Row>
            <Row label="Instructions">{agent.instructions ? <span className="whitespace-pre-wrap">{agent.instructions}</span> : "None"}</Row>
            <Row label="Type"><span className="capitalize">{agent.type}</span></Row>
            <Row label="Tags">{agent.tags.length ? agent.tags.join(", ") : "None"}</Row>
            <Row label="Created"><span title={new Date(agent.created_at).toLocaleString()}>{relativeTime(agent.created_at, now)}</span></Row>
            <Row label="Updated"><span title={new Date(agent.updated_at).toLocaleString()}>{relativeTime(agent.updated_at, now)}</span></Row>
            <Row label="Agent ID"><span className="flex items-center gap-1"><span className="truncate font-mono text-[11px]">{agent.id}</span><CopyButton value={agent.id} label="Copy Agent ID" /></span></Row>
            {Object.keys(agent.metadata).length > 0 && <Row label="Metadata"><JsonView value={agent.metadata} /></Row>}
          </dl>
        )}

        {tab === "runs" && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={onTestRun} loading={testRunPending} disabled={activeRun !== undefined || agent.status === "stopped" || agent.status === "created" || agent.status === "initializing"} icon={<FlaskConical aria-hidden className="h-3.5 w-3.5" />}>
                Start a test run
              </Button>
              <Link href={`/monitoring${operationsQuery({ agentId: agent.id })}`} className={buttonClasses("ghost", "sm")}>All runs in Operations<ArrowUpRight aria-hidden className="h-3.5 w-3.5" /></Link>
            </div>
            <p className="text-[11px] leading-4 text-muted-foreground">A test run checks the execution pipeline with a short placeholder task. It doesn&apos;t contact the model or use any tools.</p>
            {executions.length === 0 ? (
              <EmptyState title="No runs yet" description="Chat turns and test runs for this Agent appear here." />
            ) : (
              <ul className="divide-y divide-border rounded-md border border-border">
                {executions.slice(0, 30).map((execution) => (
                  <li key={execution.execution_id} className="flex flex-col gap-1.5 px-3 py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <span className="line-clamp-2 min-w-0 break-words text-xs text-foreground">{executionLabel(execution, agent.name)}</span>
                      <StatusBadge status={execution.status} className="shrink-0" />
                    </div>
                    <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                      <time dateTime={execution.created_at} title={new Date(execution.created_at).toLocaleString()}>{relativeTime(execution.created_at, now)}</time>
                      {execution.duration !== null && <><span aria-hidden>·</span><span>{formatDuration(execution.duration)}</span></>}
                      <span aria-hidden>·</span>
                      <Link href={`/monitoring${operationsQuery({ execution: execution.execution_id })}`} className="inline-flex items-center gap-0.5 hover:text-foreground">Inspect<ArrowUpRight aria-hidden className="h-3 w-3" /></Link>
                      {isActive(execution.status) && (
                        <Button size="sm" variant="ghost" className="ml-auto h-6 px-2 text-[11px]" onClick={() => onCancelRun(execution.execution_id)} loading={cancellingIds.has(execution.execution_id)} icon={<Square aria-hidden className="h-3 w-3" />}>Cancel</Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {executions.length > 30 && <p className="text-[11px] text-muted-foreground">Showing the 30 most recent runs. See all of them in Operations.</p>}
          </div>
        )}

        {tab === "runtime" && (
          context === undefined ? (
            <div className="flex flex-col gap-2" aria-busy="true"><Skeleton className="h-4 w-1/2" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-20 w-full" /></div>
          ) : context === null ? (
            <EmptyState title="No runtime context" description="The runtime has no context for this Agent right now." />
          ) : (
            <dl className="divide-y divide-border">
              <Row label="State"><StatusBadge status={context.current_state} /></Row>
              <Row label="Current task">{context.current_task || "No active task"}</Row>
              <Row label="Session"><span className="font-mono text-[11px]">{context.session_id}</span></Row>
              <Row label="Runtime metadata">{Object.keys(context.runtime_metadata).length ? <JsonView value={context.runtime_metadata} /> : "None yet"}</Row>
              <Row label="Temporary variables">{Object.keys(context.temporary_variables).length ? <JsonView value={context.temporary_variables} /> : "None during idle"}</Row>
            </dl>
          )
        )}

        {tab === "lifecycle" && (
          agentEvents.length === 0 ? (
            <EmptyState title="No lifecycle events retained" description="Events are kept in memory since the backend last started." />
          ) : (
            <ol className="flex flex-col">
              {agentEvents.map((event) => (
                <li key={event.id} className="flex items-start justify-between gap-3 border-b border-border py-2 last:border-0">
                  <span className="min-w-0">
                    <span className="block text-xs text-foreground">{describeEvent(event, { [agent.id]: agent.name })}</span>
                    <span className="block font-mono text-[11px] text-muted-foreground">{event.event_type}</span>
                  </span>
                  <time dateTime={event.timestamp} title={new Date(event.timestamp).toLocaleString()} className="shrink-0 text-[11px] text-muted-foreground">{relativeTime(event.timestamp, now)}</time>
                </li>
              ))}
            </ol>
          )
        )}
      </div>
    </Dialog>
  );
}
