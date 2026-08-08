"use client";

import { useState } from "react";
import { Bot, CheckCircle2, CircleStop, PauseCircle, PlayCircle, Plus, XCircle } from "lucide-react";

import { AgentCard } from "@/components/agents/agent-card";
import { AgentListSkeleton } from "@/components/agents/agent-list-skeleton";
import { CreateAgentDialog } from "@/components/agents/create-agent-dialog";
import { ErrorState } from "@/components/dashboard/error-state";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { RealtimeStatus } from "@/components/dashboard/realtime-status";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { useAgents } from "@/hooks/use-agents";

export default function AgentsPage() {
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const {
    agents,
    events,
    contexts,
    loading,
    error,
    pendingAgentIds,
    connectionStatus,
    latestAgentEvent,
    createAgent,
    runLifecycleAction,
    loadContext,
    retry,
  } = useAgents();

  const summaries = [
    { label: "Total agents", value: agents.length, icon: Bot, tone: "text-foreground" },
    { label: "Running", value: agents.filter((agent) => agent.status === "running").length, icon: PlayCircle, tone: "text-emerald-300" },
    { label: "Paused", value: agents.filter((agent) => agent.status === "paused").length, icon: PauseCircle, tone: "text-amber-300" },
    { label: "Stopped", value: agents.filter((agent) => agent.status === "stopped").length, icon: CircleStop, tone: "text-slate-300" },
    { label: "Completed", value: agents.filter((agent) => agent.status === "completed").length, icon: CheckCircle2, tone: "text-emerald-300" },
    { label: "Failed", value: agents.filter((agent) => agent.status === "failed").length, icon: XCircle, tone: "text-red-300" },
  ];

  async function submitCreate(input: Parameters<typeof createAgent>[0]): Promise<boolean> {
    setCreating(true);
    try {
      return await createAgent(input);
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="flex h-screen w-full overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 sm:py-8">
          <div className="mx-auto flex max-w-6xl flex-col gap-6">
            <RealtimeNotifications events={latestAgentEvent ? [latestAgentEvent] : []} />
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Bot className="h-5 w-5 text-primary" />
                  <h1 className="text-2xl font-semibold tracking-tight text-foreground">Agents</h1>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  Create and manage Agent Runtime lifecycle records.
                </p>
                <div className="mt-2">
                  <RealtimeStatus
                    connectionStatus={connectionStatus}
                    runtimeState="agent runtime"
                    lastHeartbeat={null}
                  />
                </div>
              </div>
              <button
                type="button"
                onClick={() => setCreateDialogOpen(true)}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white shadow-sm shadow-primary/20 transition-all hover:-translate-y-0.5 hover:bg-primary/85 hover:shadow-md hover:shadow-primary/20 active:translate-y-0"
              >
                <Plus className="h-4 w-4" />
                Create Agent
              </button>
            </div>

            {!loading && agents.length > 0 && (
              <section aria-label="Agent statistics" className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
                {summaries.map(({ label, value, icon: Icon, tone }) => (
                  <div key={label} className="rounded-xl border border-border bg-surface px-4 py-3 shadow-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-muted-foreground">{label}</span>
                      <Icon className={`h-4 w-4 ${tone}`} />
                    </div>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{value}</p>
                  </div>
                ))}
              </section>
            )}

            {error && !loading && agents.length === 0 ? (
              <ErrorState message={error} onRetry={() => void retry()} />
            ) : (
              <>
                {error && (
                  <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
                    {error}
                  </div>
                )}
                {loading ? (
                  <AgentListSkeleton />
                ) : agents.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-border bg-surface px-6 py-14 text-center shadow-sm">
                    <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-primary/20 bg-primary/10">
                      <Bot className="h-6 w-6 text-primary" />
                    </div>
                    <h2 className="mt-4 text-lg font-semibold text-foreground">No Agents Yet</h2>
                    <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                      Create your first Agent Runtime to begin managing intelligent workflows.
                    </p>
                    <button type="button" onClick={() => setCreateDialogOpen(true)} className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/85">
                      <Plus className="h-4 w-4" /> Create Agent
                    </button>
                  </div>
                ) : (
                  <div className="grid gap-4">
                    {agents.map((agent) => (
                      <AgentCard
                        key={agent.id}
                        agent={agent}
                        context={contexts[agent.id]}
                        events={events}
                        pending={pendingAgentIds.has(agent.id)}
                        onAction={runLifecycleAction}
                        onLoadContext={loadContext}
                      />
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </div>
      <CreateAgentDialog
        open={createDialogOpen}
        pending={creating}
        onClose={() => setCreateDialogOpen(false)}
        onSubmit={submitCreate}
      />
    </div>
  );
}
