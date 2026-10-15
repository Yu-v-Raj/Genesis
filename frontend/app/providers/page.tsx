"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Cpu, FlaskConical, KeyRound, RefreshCw, XCircle } from "lucide-react";

import { AgentAvatar } from "@/components/agents/agent-avatar";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { Button } from "@/components/ui/button";
import { Disclosure } from "@/components/ui/disclosure";
import { Alert, EmptyState, Skeleton } from "@/components/ui/feedback";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { useNow } from "@/hooks/use-now";
import { useProviders } from "@/hooks/use-providers";
import { useRealtime } from "@/hooks/use-realtime";
import { formatDuration, relativeTime } from "@/lib/operations";
import { agentsUsingModel, modelCalls, providerReadiness, redactSecrets, testFailureTitle, type ProviderReadiness } from "@/lib/providers";
import { LlmApiError, LlmService, type GenerateResult } from "@/services/llm.service";
import type { Agent, LLMModelOption } from "@/types/agents";

const STATES: readonly { status: string; meaning: string }[] = [
  { status: "not_configured", meaning: "No API key is set on the server." },
  { status: "configured", meaning: "A key is set, but no request has proven it works yet." },
  { status: "provider_responding", meaning: "A real request succeeded recently." },
  { status: "provider_failing", meaning: "The most recent real request failed." },
];

export default function ProvidersPage() {
  const realtime = useRealtime();
  const { data, loading, error, eventsError, reload } = useProviders(realtime);
  const now = useNow();
  const readiness = data ? providerReadiness(data.models, data.events) : [];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-5 px-4 py-6 sm:px-6 sm:py-8">
      <RealtimeNotifications events={realtime.latestEvent ? [realtime.latestEvent] : []} />
      <PageHeader
        title="Model providers"
        description="The AI models your Agents can use, and whether they're actually answering. API keys stay on the server and are never shown here."
        actions={<Button size="sm" onClick={() => void reload()} loading={loading && data !== null} icon={<RefreshCw aria-hidden className="h-3.5 w-3.5" />}>Refresh</Button>}
      />

      {error && data === null ? (
        <Alert tone="danger" action={<Button size="sm" onClick={() => void reload()} loading={loading}>Try again</Button>}>
          <p className="font-medium">Provider information couldn&apos;t be loaded.</p>
          <p className="mt-0.5 text-xs text-muted-foreground">{redactSecrets(error)}</p>
        </Alert>
      ) : data === null ? (
        <div className="flex flex-col gap-3" aria-busy="true" aria-label="Loading providers"><Skeleton className="h-40 w-full" /><Skeleton className="h-40 w-full" /></div>
      ) : (
        <>
          {error && <Alert tone="warning">Couldn&apos;t refresh: {redactSecrets(error)}</Alert>}
          {eventsError && <Alert tone="warning">Recent model calls couldn&apos;t be loaded, so status below is based on configuration only.</Alert>}
          {readiness.length === 0 ? (
            <EmptyState icon={Cpu} title="No model providers registered" description="The server doesn't register any model providers, so Agents can't answer yet." />
          ) : (
            readiness.map((provider) => (
              <ProviderCard key={provider.provider} provider={provider} models={data.models.filter((model) => model.provider === provider.provider)}
                agents={data.agents} calls={modelCalls(data.events, provider.provider)} now={now} />
            ))
          )}
          {data.providers.some((name) => !data.models.some((model) => model.provider === name)) && (
            <p className="text-xs text-muted-foreground">Registered without models: {data.providers.filter((name) => !data.models.some((model) => model.provider === name)).join(", ")}.</p>
          )}

          <Disclosure summary="What the statuses mean">
            <dl className="flex flex-col gap-2">
              {STATES.map((item) => (
                <div key={item.status} className="flex flex-wrap items-center gap-2 text-xs">
                  <dt><StatusBadge status={item.status} /></dt><dd className="text-muted-foreground">{item.meaning}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              Outcomes come from model calls since the backend last started. Keys and models are set in the server&apos;s environment
              (an administrator edits the backend <code className="font-mono">.env</code> and restarts it); they can&apos;t be changed here.
            </p>
          </Disclosure>
        </>
      )}
    </div>
  );
}

function ProviderCard({ provider, models, agents, calls, now }: { provider: ProviderReadiness; models: LLMModelOption[]; agents: Agent[]; calls: ReturnType<typeof modelCalls>; now: Date }) {
  const { evidence } = provider;
  return (
    <Panel aria-labelledby={`provider-${provider.provider}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-4 py-3.5">
        <div className="min-w-0">
          <h2 id={`provider-${provider.provider}`} className="text-base font-semibold text-foreground">{provider.label}</h2>
          <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
            {!provider.configured ? "No API key is set on the server for this provider."
              : evidence.kind === "success" ? `Last real response ${relativeTime(evidence.at, now)}${evidence.model ? ` from ${evidence.model}` : ""}.`
              : evidence.kind === "failure" ? `Last real request failed ${relativeTime(evidence.at, now)}: ${evidence.reason}`
              : "A key is set. No request has been made since the backend started, so it isn't verified yet."}
          </p>
        </div>
        <StatusBadge status={provider.state} />
      </div>

      <ul aria-label={`${provider.label} models`} className="divide-y divide-border">
        {models.map((model) => <ModelRow key={model.model_name} model={model} agents={agentsUsingModel(agents, model.provider, model.model_name)} />)}
      </ul>

      <div className="border-t border-border p-3">
        <Disclosure summary={`Recent model calls (${calls.length})`}>
          {calls.length === 0 ? (
            <p className="text-xs text-muted-foreground">None recorded since the backend started.</p>
          ) : (
            <ul className="flex flex-col divide-y divide-border">
              {calls.slice(0, 20).map((call) => (
                <li key={call.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-xs">
                  {call.ok ? <CheckCircle2 aria-hidden className="h-3.5 w-3.5 text-success" /> : <XCircle aria-hidden className="h-3.5 w-3.5 text-danger" />}
                  <span className="text-foreground">{call.ok ? "Responded" : "Failed"}</span>
                  {call.model && <span className="font-mono text-[11px] text-muted-foreground">{call.model}</span>}
                  {call.durationMs !== null && <span className="text-muted-foreground">{formatDuration(call.durationMs / 1000)}</span>}
                  {call.totalTokens !== null && <span className="text-muted-foreground">{call.totalTokens} tokens</span>}
                  {call.reason && <span className="w-full text-muted-foreground sm:w-auto">{call.reason}</span>}
                  <time dateTime={call.at} title={new Date(call.at).toLocaleString()} className="ml-auto text-[11px] text-subtle">{relativeTime(call.at, now)}</time>
                </li>
              ))}
            </ul>
          )}
        </Disclosure>
      </div>
    </Panel>
  );
}

type TestState = { phase: "idle" } | { phase: "running" } | { phase: "done"; result: GenerateResult; ms: number } | { phase: "failed"; title: string; detail: string };

function ModelRow({ model, agents }: { model: LLMModelOption; agents: Agent[] }) {
  const configured = model.metadata?.configured === true;
  const [test, setTest] = useState<TestState>({ phase: "idle" });
  const inFlight = useRef(false);

  /** One real request through the server's integration-check endpoint, only on click. */
  async function runTest() {
    if (inFlight.current || !configured) return;
    inFlight.current = true;
    setTest({ phase: "running" });
    const started = performance.now();
    try {
      const result = await LlmService.testModel({ provider: model.provider, model_name: model.model_name });
      setTest({ phase: "done", result, ms: performance.now() - started });
    } catch (cause) {
      const status = cause instanceof LlmApiError ? cause.status : undefined;
      setTest({ phase: "failed", title: testFailureTitle(status), detail: redactSecrets(cause instanceof Error ? cause.message : "") });
    } finally {
      inFlight.current = false;
    }
  }

  return (
    <li className="flex flex-col gap-3 px-4 py-3.5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="break-all font-mono text-sm text-foreground">{model.model_name}</p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1"><KeyRound aria-hidden className="h-3 w-3" />{configured ? "Key configured" : "No API key"}</span>
            {model.capabilities.length > 0 && <span>Supports: {model.capabilities.join(", ")}</span>}
          </p>
        </div>
        <Button size="sm" onClick={() => void runTest()} disabled={!configured} loading={test.phase === "running"} icon={<FlaskConical aria-hidden className="h-3.5 w-3.5" />}
          title={configured ? "Sends one short real request to this model" : "Add an API key on the server first"}>
          {test.phase === "running" ? "Testing…" : "Send test request"}
        </Button>
      </div>

      <div aria-live="polite">
        {test.phase === "done" && (
          <Alert tone="success">
            <span className="text-xs">Connected — {model.model_name} answered in {formatDuration(test.ms / 1000)} using {test.result.usage.total_tokens} tokens.{test.result.content?.trim() ? <> Reply: <q className="break-words">{test.result.content.trim().slice(0, 80)}</q></> : " It returned no visible text within the test's short reply limit, which is still a successful response."}</span>
          </Alert>
        )}
        {test.phase === "failed" && (
          <Alert tone="danger">
            <p className="text-xs font-medium">{test.title}</p>
            {test.detail && <p className="mt-0.5 break-words text-xs text-muted-foreground">{test.detail}</p>}
          </Alert>
        )}
      </div>

      <div className="text-xs">
        <p className="mb-1.5 text-muted-foreground">{agents.length === 0 ? "No Agent uses this model." : `Used by ${agents.length} Agent${agents.length === 1 ? "" : "s"}:`}</p>
        {agents.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {agents.map((agent) => (
              <li key={agent.id}>
                <Link href={`/agents?agent=${agent.id}`} className="inline-flex max-w-56 items-center gap-2 rounded-md border border-border bg-surface-2 py-1 pl-1 pr-2.5 text-foreground hover:border-border-strong">
                  <AgentAvatar name={agent.name} size="sm" /><span className="truncate">{agent.name}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}
