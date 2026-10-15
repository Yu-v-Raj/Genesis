"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Activity, ArrowRight, Bot, BrainCircuit, ChevronRight, MessageSquare, Plus, Sparkles } from "lucide-react";

import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { Button, buttonClasses } from "@/components/ui/button";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { StatusBadge, StatusDot } from "@/components/ui/status-badge";
import { useAgentOptions } from "@/hooks/use-agent-options";
import { useMonitoring } from "@/hooks/use-monitoring";
import { useNow } from "@/hooks/use-now";
import { executionLabel } from "@/lib/durable-work";
import { countLabel, operationsQuery, relativeTime, summarizeAgents, summarizeExecutions } from "@/lib/operations";
import { providerReadiness, type ProviderReadiness } from "@/lib/providers";
import { cn } from "@/lib/utils";

const RECENT = 6;
const reveal = { initial: { opacity: 0, y: 4 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.18, ease: "easeOut" } } as const;

export default function OverviewPage() {
  // eventLimit: model-call outcomes for provider readiness can be far back behind heartbeats.
  const { data, loading, error, retry } = useMonitoring({ eventLimit: 1000 });
  const options = useAgentOptions();
  const now = useNow();

  const agentNames: Record<string, string> = Object.fromEntries((data?.agents ?? []).map((agent) => [agent.id, agent.name]));
  const agents = data ? summarizeAgents(data.agents.map((agent) => agent.status)) : null;
  const runs = data ? summarizeExecutions(data.executions, now) : null;
  const providers = options.models && data ? providerReadiness(options.models, data.events) : null;
  const configured = providers?.filter((provider) => provider.configured).length ?? 0;
  const responding = providers?.find((provider) => provider.state === "provider_responding");

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-8 sm:px-6 sm:py-10">
      {data && <RealtimeNotifications events={data.events.slice(0, 5)} />}

      <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">Your Agent workspace</h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
            Create AI Agents, give them tools and memory, and see everything they do — all in one place.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Link href="/agents" className={buttonClasses("ghost")}>Open Agents</Link>
          <Link href="/agents?create=1" className={buttonClasses("primary", "md", "px-4")}>
            <Plus aria-hidden className="h-4 w-4" />Create Agent
          </Link>
        </div>
      </header>

      {error && data === null ? (
        <Alert tone="danger" action={<Button size="sm" onClick={() => void retry()} loading={loading}>Try again</Button>}>
          <p className="font-medium">Your workspace couldn&apos;t be loaded.</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{error}</p>
        </Alert>
      ) : (
        <>
          {error && <Alert tone="warning" action={<Button size="sm" onClick={() => void retry()} loading={loading}>Refresh</Button>}>Couldn&apos;t refresh: {error}</Alert>}

          {/* One quiet strip of the few numbers that matter, each leading somewhere useful. */}
          <section aria-label="Workspace summary" className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border lg:grid-cols-4">
            {agents === null || runs === null ? (
              Array.from({ length: 4 }, (_, index) => <div key={index} className="bg-surface p-4"><Skeleton className="h-3 w-20" /><Skeleton className="mt-3 h-7 w-12" /><Skeleton className="mt-2 h-3 w-28" /></div>)
            ) : (
              <>
                <SummaryTile href="/agents" label="Agents" value={String(agents.total)}
                  detail={agents.total === 0 ? "None yet" : [`${agents.ready} ready`, agents.working ? `${agents.working} working` : null, agents.other ? `${agents.other} other` : null].filter(Boolean).join(" · ")} />
                <SummaryTile href="/monitoring" label="Runs today" value={countLabel(runs.last24h, runs.capped)}
                  detail={runs.last24h === 0 ? "Nothing in the last 24 hours" : `${countLabel(runs.completed24h, runs.capped)} completed in the last 24 hours`} />
                <SummaryTile href={`/monitoring${operationsQuery({ status: "attention" })}`} label="Needs attention" value={countLabel(runs.attention24h, runs.capped)}
                  tone={runs.attention24h ? "danger" : undefined}
                  detail={runs.attention24h ? "Failed or interrupted runs to review" : "Nothing failed in the last 24 hours"} />
                <SummaryTile href="/providers" label="Model providers"
                  value={providers ? `${configured} of ${providers.length}` : options.error ? "—" : "…"}
                  detail={options.error ? "Status unavailable" : !providers ? "Checking…" : responding ? `${responding.label} responded ${relativeTime(responding.evidence.kind === "success" ? responding.evidence.at : null, now)}` : configured ? "Configured, not yet verified by a request" : "No provider has an API key yet"} />
              </>
            )}
          </section>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
            <motion.div {...reveal} className="min-w-0 lg:col-span-3">
              <RecentActivity data={data} agentNames={agentNames} now={now} />
            </motion.div>
            <motion.div {...reveal} className="min-w-0 lg:col-span-2">
              <ProvidersPanel providers={providers} unavailable={options.error !== null && options.models === null} now={now} />
            </motion.div>
          </div>
        </>
      )}
    </div>
  );
}

function SummaryTile({ href, label, value, detail, tone }: { href: string; label: string; value: string; detail: string; tone?: "danger" }) {
  return (
    <Link href={href} className="group flex flex-col bg-surface p-4 transition-colors hover:bg-surface-2">
      <span className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">{tone && <StatusDot tone={tone} />}{label}</span>
        <ChevronRight aria-hidden className="h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
      </span>
      <span className={cn("mt-1.5 text-2xl font-semibold tabular-nums tracking-tight", tone ? "text-danger" : "text-foreground")}>{value}</span>
      <span className="mt-0.5 text-[11px] leading-4 text-muted-foreground">{detail}</span>
    </Link>
  );
}

function RecentActivity({ data, agentNames, now }: { data: ReturnType<typeof useMonitoring>["data"]; agentNames: Record<string, string>; now: Date }) {
  if (data === null) {
    return (
      <Panel>
        <PanelHeader title="Recent activity" />
        <div className="flex flex-col gap-3 p-4" aria-busy="true">{Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-10 w-full" />)}</div>
      </Panel>
    );
  }
  if (data.agents.length === 0) return <GetStarted />;

  const recent = data.executions.slice(0, RECENT);
  return (
    <Panel>
      <PanelHeader title="Recent activity" description="The latest chat turns and tasks across your Agents."
        actions={recent.length > 0 && <Link href="/monitoring" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">All runs<ArrowRight aria-hidden className="h-3 w-3" /></Link>} />
      {recent.length === 0 ? (
        <EmptyState icon={MessageSquare} title="No runs yet" description="Open an Agent and send it a message. Each turn shows up here." className="m-4 border-none"
          action={<Link href="/agents" className={buttonClasses("secondary", "sm")}>Open Agents</Link>} />
      ) : (
        <ul className="divide-y divide-border">
          {recent.map((execution) => (
            <li key={execution.execution_id}>
              <Link href={`/monitoring${operationsQuery({ execution: execution.execution_id })}`} className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-white/[0.025]">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-foreground">{executionLabel(execution, agentNames[execution.agent_id])}</span>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground">
                    <time dateTime={execution.created_at} title={new Date(execution.created_at).toLocaleString()}>{relativeTime(execution.created_at, now)}</time>
                    {execution.status === "failed" || execution.status === "interrupted" ? " · Open to review and retry" : ""}
                  </span>
                </span>
                <StatusBadge status={execution.status} className="shrink-0" />
                <ChevronRight aria-hidden className="h-4 w-4 shrink-0 text-subtle transition-colors group-hover:text-muted-foreground" />
                <span className="sr-only">Inspect this run</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function GetStarted() {
  const steps = [
    { icon: Bot, title: "Create an Agent", text: "Describe what it should do and pick a model." },
    { icon: MessageSquare, title: "Chat with it", text: "Ask questions or give it tasks; it can use the tools you allow." },
    { icon: BrainCircuit, title: "Teach it", text: "Save facts and preferences it should remember." },
    { icon: Activity, title: "Follow its work", text: "Every run is recorded in Operations with its full timeline." },
  ];
  return (
    <Panel>
      <PanelHeader title="Get started" description="Your workspace is empty. Four steps to your first Agent:" />
      <ol className="grid gap-px bg-border sm:grid-cols-2">
        {steps.map((step, index) => (
          <li key={step.title} className="flex gap-3 bg-surface p-4">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-surface-2 text-xs text-muted-foreground">{index + 1}</span>
            <span><span className="block text-sm font-medium text-foreground">{step.title}</span><span className="mt-0.5 block text-xs leading-5 text-muted-foreground">{step.text}</span></span>
          </li>
        ))}
      </ol>
      <div className="border-t border-border p-4">
        <Link href="/agents?create=1" className={buttonClasses("primary", "sm")}><Sparkles aria-hidden className="h-3.5 w-3.5" />Create your first Agent</Link>
      </div>
    </Panel>
  );
}

function ProvidersPanel({ providers, unavailable, now }: { providers: ProviderReadiness[] | null; unavailable: boolean; now: Date }) {
  return (
    <Panel id="model-providers" className="scroll-mt-6">
      <PanelHeader title="Model providers" description="Which AI models your Agents can use."
        actions={<Link href="/providers" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">Details<ArrowRight aria-hidden className="h-3 w-3" /></Link>} />
      {unavailable ? (
        <div className="flex items-center justify-between gap-3 p-4">
          <p className="text-sm text-muted-foreground">Provider status couldn&apos;t be loaded.</p>
          <StatusBadge status="unavailable" />
        </div>
      ) : providers === null ? (
        <div className="flex flex-col gap-3 p-4" aria-busy="true"><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" /></div>
      ) : providers.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">This Genesis server doesn&apos;t offer any models.</p>
      ) : (
        <ul className="divide-y divide-border">
          {providers.map((provider) => (
            <li key={provider.provider} className="flex flex-col gap-1.5 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-foreground">{provider.label}</span>
                <StatusBadge status={provider.state} />
              </div>
              <p className="truncate font-mono text-[11px] text-muted-foreground" title={provider.models.join(", ")}>{provider.models.join(", ")}</p>
              <p className="text-xs leading-5 text-muted-foreground">{evidenceText(provider, now)}</p>
            </li>
          ))}
        </ul>
      )}
      <p className="border-t border-border px-4 py-3 text-[11px] leading-4 text-muted-foreground">
        &ldquo;Configured&rdquo; means an API key is set on the server; it doesn&apos;t prove requests succeed. Outcomes come from model calls since the backend last started.
      </p>
    </Panel>
  );
}

function evidenceText(provider: ProviderReadiness, now: Date): string {
  if (!provider.configured) return `Add an API key for ${provider.label} on the server to use these models.`;
  const { evidence } = provider;
  if (evidence.kind === "success") return `Last response ${relativeTime(evidence.at, now)}${evidence.model ? ` from ${evidence.model}` : ""}.`;
  if (evidence.kind === "failure") return `Last request failed ${relativeTime(evidence.at, now)}. ${evidence.reason}`;
  return "Not verified yet: no requests since the backend started.";
}
