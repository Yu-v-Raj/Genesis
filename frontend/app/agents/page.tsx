"use client";

import { useState } from "react";
import { Bot, CheckCircle2, ChevronDown, CircleStop, Clock3, Gauge, PlayCircle, Plus, TimerReset, XCircle } from "lucide-react";

import { AgentCard } from "@/components/agents/agent-card";
import { AgentConversation, ReadinessBadge } from "@/components/agents/agent-conversation";
import { AgentListSkeleton } from "@/components/agents/agent-list-skeleton";
import { AgentSettingsDialog } from "@/components/agents/agent-settings-dialog";
import { ErrorState } from "@/components/dashboard/error-state";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { RealtimeStatus } from "@/components/dashboard/realtime-status";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { useAgentConversation } from "@/hooks/use-agent-conversation";
import { useAgentOptions } from "@/hooks/use-agent-options";
import { useAgents } from "@/hooks/use-agents";
import { useExecutions } from "@/hooks/use-executions";
import { useRealtime } from "@/hooks/use-realtime";
import { agentReadiness, modelLabel } from "@/lib/agent-experience";
import type { Agent } from "@/types/agents";

/** `undefined` = closed, `null` = creating, an Agent = editing that Agent. */
type SettingsTarget = Agent | null | undefined;

export default function AgentsPage() {
  const [settingsTarget, setSettingsTarget] = useState<SettingsTarget>(undefined);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const realtime = useRealtime();
  const options = useAgentOptions();
  const {
    agents, events, contexts, loading, error, pendingAgentIds, connectionStatus,
    createAgent, updateConfiguration, upsertAgent, runLifecycleAction, loadContext, retry,
  } = useAgents(realtime);
  const selectedAgent = agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null;
  const conversation = useAgentConversation(selectedAgent?.id ?? null, upsertAgent);
  const executionState = useExecutions(realtime);
  const combinedError = error ?? executionState.error;
  const initialLoading = loading || executionState.loading;
  const readinessFor = (agent: Agent) => agentReadiness(agent, options.models);

  async function create(input: Parameters<typeof createAgent>[0]) {
    const agent = await createAgent(input);
    if (agent) setSelectedAgentId(agent.id);
    return agent;
  }

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
          <div className="mx-auto flex max-w-6xl flex-col gap-6">
            <RealtimeNotifications events={realtime.latestEvent ? [realtime.latestEvent] : []} />
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Bot className="h-5 w-5 text-primary" aria-hidden="true" />
                  <h1 className="text-2xl font-semibold tracking-tight text-foreground">Agents</h1>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">Create an Agent, choose the model and tools it may use, then chat with it.</p>
                <div className="mt-2">
                  <RealtimeStatus connectionStatus={connectionStatus} runtimeState="agent runtime" lastHeartbeat={null} />
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSettingsTarget(null)}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white shadow-sm shadow-primary/20 transition-all hover:-translate-y-0.5 hover:bg-primary/85 active:translate-y-0"
              >
                <Plus className="h-4 w-4" aria-hidden="true" />
                Create Agent
              </button>
            </div>

            {combinedError && !initialLoading && agents.length === 0 ? (
              <ErrorState message={combinedError} onRetry={() => void Promise.all([retry(), executionState.retry(), options.reload()])} />
            ) : (
              <>
                {combinedError && (
                  <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
                    <span>{combinedError}</span>
                    <button type="button" onClick={() => void Promise.all([retry(), executionState.retry()])} className="rounded-md border border-red-400/25 px-3 py-1.5 text-xs font-medium text-red-100 transition-colors hover:bg-red-400/10">Retry</button>
                  </div>
                )}
                {initialLoading ? (
                  <AgentListSkeleton />
                ) : agents.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-border bg-surface px-6 py-14 text-center shadow-sm">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
                      <Bot className="h-6 w-6 text-primary" aria-hidden="true" />
                    </div>
                    <h2 className="mt-4 text-lg font-semibold text-foreground">No Agents yet</h2>
                    <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                      Create your first Agent, pick a model and the tools it may use, and ask it to do something — for example, “Calculate 25 × 4”.
                    </p>
                    <button type="button" onClick={() => setSettingsTarget(null)} className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/85">
                      <Plus className="h-4 w-4" aria-hidden="true" /> Create Agent
                    </button>
                  </div>
                ) : (
                  <>
                    <section className="grid gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
                      <nav aria-label="Your Agents" className="rounded-xl border border-border bg-surface p-2 shadow-sm lg:max-h-[calc(100vh-12rem)] lg:overflow-y-auto">
                        <ul className="grid gap-1">
                          {agents.map((agent) => {
                            const selected = agent.id === selectedAgent?.id;
                            return (
                              <li key={agent.id}>
                                <button
                                  type="button"
                                  onClick={() => setSelectedAgentId(agent.id)}
                                  aria-current={selected ? "true" : undefined}
                                  className={`w-full rounded-lg px-3 py-2.5 text-left transition-colors ${selected ? "bg-primary/10 ring-1 ring-primary/40" : "hover:bg-white/[0.04]"}`}
                                >
                                  <span className="block truncate text-sm font-medium text-foreground">{agent.name}</span>
                                  <span className="mt-1 block truncate text-xs text-muted-foreground">
                                    {agent.llm_model ? modelLabel(agent.llm_model) : "No model selected"}
                                  </span>
                                  <span className="mt-1.5 block"><ReadinessBadge readiness={readinessFor(agent)} /></span>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </nav>
                      <AgentConversation
                        key={selectedAgent?.id}
                        agent={selectedAgent}
                        readiness={selectedAgent ? readinessFor(selectedAgent) : null}
                        messages={conversation.messages}
                        pendingMessage={conversation.pendingMessage}
                        problem={conversation.problem}
                        loadError={conversation.loadError}
                        onSend={conversation.send}
                        onConfigure={() => selectedAgent && setSettingsTarget(selectedAgent)}
                        onInitialize={() => selectedAgent && void runLifecycleAction(selectedAgent.id, "initialize")}
                        onDismissProblem={conversation.dismissProblem}
                      />
                    </section>
                    <RuntimeDetails
                      agents={agents}
                      executionState={executionState}
                      events={events}
                      contexts={contexts}
                      pendingAgentIds={pendingAgentIds}
                      onAction={runLifecycleAction}
                      onLoadContext={loadContext}
                    />
                  </>
                )}
              </>
            )}
          </div>
        </main>
      </div>
      {settingsTarget !== undefined && (
        <AgentSettingsDialog
          key={settingsTarget?.id ?? "new"}
          agent={settingsTarget}
          models={options.models}
          tools={options.tools}
          optionsError={options.error}
          onClose={() => setSettingsTarget(undefined)}
          onCreate={create}
          onUpdate={updateConfiguration}
        />
      )}
    </div>
  );
}

/** Lifecycle records, contexts, and executions for engineers; collapsed by default. */
function RuntimeDetails({
  agents, executionState, events, contexts, pendingAgentIds, onAction, onLoadContext,
}: {
  agents: Agent[];
  executionState: ReturnType<typeof useExecutions>;
  events: ReturnType<typeof useAgents>["events"];
  contexts: ReturnType<typeof useAgents>["contexts"];
  pendingAgentIds: ReadonlySet<string>;
  onAction: ReturnType<typeof useAgents>["runLifecycleAction"];
  onLoadContext: (agentId: string) => Promise<void>;
}) {
  const executions = executionState.executions;
  const completed = executions.filter((execution) => execution.status === "completed");
  const terminal = executions.filter((execution) => ["completed", "failed", "cancelled"].includes(execution.status));
  const durations = completed.map((execution) => execution.duration).filter((duration): duration is number => duration !== null);
  const summaries = [
    { label: "Agents", value: agents.length, icon: Bot },
    { label: "Ready", value: agents.filter((agent) => agent.status === "idle").length, icon: CheckCircle2 },
    { label: "Working", value: agents.filter((agent) => agent.status === "running").length, icon: PlayCircle },
    { label: "Stopped", value: agents.filter((agent) => agent.status === "stopped").length, icon: CircleStop },
    { label: "Executions", value: executions.length, icon: Gauge },
    { label: "Failed executions", value: executions.filter((execution) => execution.status === "failed").length, icon: XCircle },
    { label: "Avg. execution", value: durations.length ? `${(durations.reduce((sum, value) => sum + value, 0) / durations.length).toFixed(1)}s` : "—", icon: TimerReset },
    { label: "Execution success", value: terminal.length ? `${Math.round((completed.length / terminal.length) * 100)}%` : "—", icon: Clock3 },
  ];
  return (
    <details className="group rounded-xl border border-border bg-surface shadow-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-sm font-medium text-foreground">
        <span>Runtime details <span className="font-normal text-muted-foreground">— lifecycle, context, and executions</span></span>
        <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="grid gap-4 border-t border-border p-4">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {summaries.map(({ label, value, icon: Icon }) => (
            <div key={label} className="rounded-lg border border-border bg-background/40 px-3 py-2">
              <dt className="flex items-center justify-between text-xs text-muted-foreground">{label}<Icon className="h-3.5 w-3.5" aria-hidden="true" /></dt>
              <dd className="mt-1 text-lg font-semibold text-foreground">{value}</dd>
            </div>
          ))}
        </dl>
        {agents.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            context={contexts[agent.id]}
            events={events}
            pending={pendingAgentIds.has(agent.id)}
            executions={executions.filter((execution) => execution.agent_id === agent.id)}
            pendingExecution={executionState.pendingAgentIds.has(agent.id) || executions.some((execution) => execution.agent_id === agent.id && executionState.pendingExecutionIds.has(execution.execution_id))}
            onAction={onAction}
            onLoadContext={onLoadContext}
            onExecute={executionState.executeAgent}
            onCancelExecution={executionState.cancelExecution}
            onLoadExecutions={executionState.loadAgentExecutions}
          />
        ))}
      </div>
    </details>
  );
}
