"use client";

import { Suspense, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Bot } from "lucide-react";

import { AgentDetails } from "@/components/agents/agent-details";
import { AgentDirectory } from "@/components/agents/agent-directory";
import { AgentSettingsDialog } from "@/components/agents/agent-settings-dialog";
import { AgentWorkspace } from "@/components/agents/agent-workspace";
import { RealtimeNotifications } from "@/components/dashboard/realtime-notifications";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert, Skeleton } from "@/components/ui/feedback";
import { useAgentConversation } from "@/hooks/use-agent-conversation";
import { useAgentOptions } from "@/hooks/use-agent-options";
import { useAgents } from "@/hooks/use-agents";
import { useExecutions } from "@/hooks/use-executions";
import { useRealtime } from "@/hooks/use-realtime";
import { activeChatExecution, sortAgents, type LifecycleAction } from "@/lib/agent-directory";
import { agentReadiness } from "@/lib/agent-experience";
import { cn } from "@/lib/utils";
import type { Agent } from "@/types/agents";

/** `undefined` = closed, `null` = creating, an Agent = editing that Agent. */
type SettingsTarget = Agent | null | undefined;

const PAGE_HEIGHT = "h-[calc(100dvh-3.5rem)]"; // the shell's top bar is h-14

export default function AgentsPage() {
  // The selected Agent and conversation live in the URL (?agent=…&session=…), so a reload
  // or a shared link reopens the same place. useSearchParams needs a Suspense boundary.
  return (
    <Suspense fallback={<AgentsSkeleton />}>
      <Agents />
    </Suspense>
  );
}

function AgentsSkeleton() {
  return (
    <div className={cn("flex", PAGE_HEIGHT)} aria-busy="true">
      <div className="w-full space-y-3 border-r border-border p-4 lg:w-80 xl:w-96"><Skeleton className="h-6 w-32" /><Skeleton className="h-9 w-full" /><Skeleton className="h-14 w-full" /><Skeleton className="h-14 w-full" /></div>
      <div className="hidden flex-1 lg:block" />
    </div>
  );
}

/**
 * Opens the create dialog when another page links to `/agents?create=1` (the Overview's
 * Create Agent action), then drops the parameter so a reload doesn't reopen it.
 */
function CreateFromLink({ onCreate }: { onCreate: () => void }) {
  const requested = useSearchParams().get("create") === "1";
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (!requested) return;
    onCreate();
    const params = new URLSearchParams(window.location.search);
    params.delete("create");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [requested, onCreate, router, pathname]);
  return null;
}

function Agents() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [settingsTarget, setSettingsTarget] = useState<SettingsTarget>(undefined);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [confirm, setConfirm] = useState<{ agent: Agent; action: "stop" | "delete" } | null>(null);

  const realtime = useRealtime();
  const options = useAgentOptions();
  const {
    agents: unsortedAgents, events, contexts, loading, error, pendingAgentIds, connectionStatus,
    createAgent, updateConfiguration, upsertAgent, runLifecycleAction, loadContext, retry,
  } = useAgents(realtime);
  const executionState = useExecutions(realtime);

  const agents = sortAgents(unsortedAgents);
  const requestedAgentId = params.get("agent");
  const requestedSessionId = params.get("session");
  const selected = agents.find((agent) => agent.id === requestedAgentId) ?? null;
  // Wide screens always show a workspace (the newest Agent by default); narrow screens
  // show the list until an Agent is chosen.
  const shown = selected ?? agents[0] ?? null;
  const conversation = useAgentConversation(shown?.id ?? null, upsertAgent, selected ? requestedSessionId : null);

  // Keep the open conversation in the URL once the user has chosen an Agent.
  useEffect(() => {
    if (!selected || !conversation.sessionId || conversation.sessionAgentId !== selected.id) return;
    if (conversation.sessionId === requestedSessionId) return;
    router.replace(`${pathname}?agent=${selected.id}&session=${conversation.sessionId}`, { scroll: false });
  }, [selected, conversation.sessionId, conversation.sessionAgentId, requestedSessionId, router, pathname]);

  // An Agent link that no longer resolves (deleted, or never existed) returns to the list.
  useEffect(() => {
    if (!loading && requestedAgentId && unsortedAgents.length > 0 && !unsortedAgents.some((agent) => agent.id === requestedAgentId)) {
      router.replace(pathname, { scroll: false });
    }
  }, [loading, requestedAgentId, unsortedAgents, router, pathname]);

  function selectAgent(agentId: string) {
    setDetailsOpen(false);
    router.push(`${pathname}?agent=${agentId}`, { scroll: false });
  }

  async function create(input: Parameters<typeof createAgent>[0]) {
    const agent = await createAgent(input);
    if (agent) selectAgent(agent.id);
    return agent;
  }

  function lifecycle(agent: Agent, action: LifecycleAction) {
    if (action === "initialize") void runLifecycleAction(agent.id, action);
    else setConfirm({ agent, action });
  }

  async function confirmLifecycle() {
    if (!confirm) return;
    const { agent, action } = confirm;
    const done = await runLifecycleAction(agent.id, action);
    setConfirm(null);
    if (done && action === "delete" && agent.id === requestedAgentId) router.push(pathname, { scroll: false });
  }

  const readiness = shown ? agentReadiness(shown, options.models) : null;
  // Any chat run in progress for this conversation: one sent from here, a retry, or another tab.
  const liveExecution = shown ? activeChatExecution(executionState.executions, shown.id, conversation.sessionId) : null;
  const pageError = error ?? executionState.error;

  return (
    <div className={cn("flex min-h-0", PAGE_HEIGHT)}>
      <Suspense fallback={null}><CreateFromLink onCreate={() => setSettingsTarget(null)} /></Suspense>
      <RealtimeNotifications events={realtime.latestEvent ? [realtime.latestEvent] : []} />

      <aside aria-label="Agents directory" className={cn("min-h-0 w-full shrink-0 flex-col border-r border-border lg:flex lg:w-80 xl:w-96", selected ? "hidden" : "flex")}>
        {(pageError || connectionStatus === "disconnected") && (
          <div className="flex flex-col gap-2 border-b border-border p-3">
            {pageError && <Alert tone="danger" action={<Button size="sm" onClick={() => void Promise.all([retry(), executionState.retry(), options.reload()])}>Retry</Button>}><span className="text-xs">{pageError}</span></Alert>}
            {connectionStatus === "disconnected" && <Alert tone="warning"><span className="text-xs">Live updates are reconnecting; statuses may be out of date.</span></Alert>}
          </div>
        )}
        <AgentDirectory
          agents={agents}
          loading={loading && unsortedAgents.length === 0}
          selectedId={shown?.id ?? null}
          models={options.models}
          pendingIds={pendingAgentIds}
          onSelect={selectAgent}
          onCreate={() => setSettingsTarget(null)}
          onConfigure={(agent) => setSettingsTarget(agent)}
          onAction={lifecycle}
        />
      </aside>

      <div className={cn("min-h-0 min-w-0 flex-1 lg:flex", selected ? "flex" : "hidden")}>
        {shown ? (
          <AgentWorkspace
            key={shown.id}
            agent={shown}
            readiness={readiness}
            conversation={conversation}
            liveExecution={liveExecution}
            cancelling={liveExecution !== null && executionState.pendingExecutionIds.has(liveExecution.execution_id)}
            onCancelRun={(executionId) => void executionState.cancelExecution(executionId)}
            onConfigure={() => setSettingsTarget(shown)}
            onInitialize={() => void runLifecycleAction(shown.id, "initialize")}
            onOpenDetails={() => { setDetailsOpen(true); void executionState.loadAgentExecutions(shown.id); }}
            onAction={(action) => lifecycle(shown, action)}
            lifecyclePending={pendingAgentIds.has(shown.id)}
            onBack={() => router.push(pathname, { scroll: false })}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
            <Bot aria-hidden className="h-6 w-6 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">{loading ? "Loading Agents…" : "Create an Agent to start a conversation."}</p>
          </div>
        )}
      </div>

      {shown && (
        <AgentDetails
          agent={shown}
          open={detailsOpen}
          onClose={() => setDetailsOpen(false)}
          executions={executionState.executions.filter((execution) => execution.agent_id === shown.id)}
          events={events}
          context={contexts[shown.id]}
          onLoadContext={() => void loadContext(shown.id)}
          onTestRun={() => void executionState.executeAgent(shown.id)}
          testRunPending={executionState.pendingAgentIds.has(shown.id)}
          onCancelRun={(executionId) => void executionState.cancelExecution(executionId)}
          cancellingIds={executionState.pendingExecutionIds}
          error={executionState.error}
        />
      )}

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

      <Dialog
        open={confirm !== null}
        onClose={() => { if (!confirm || !pendingAgentIds.has(confirm.agent.id)) setConfirm(null); }}
        title={confirm?.action === "delete" ? `Delete ${confirm.agent.name}?` : `Stop ${confirm?.agent.name ?? "this Agent"}?`}
        description={confirm?.action === "delete"
          ? "This permanently deletes the Agent together with its conversations, memories and run history. It can't be undone."
          : "A stopped Agent can no longer chat or run work. Stopping can't be undone; afterwards the Agent can only be deleted."}
        footer={confirm && (
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button onClick={() => setConfirm(null)} disabled={pendingAgentIds.has(confirm.agent.id)} data-autofocus>Cancel</Button>
            <Button variant="danger" onClick={() => void confirmLifecycle()} loading={pendingAgentIds.has(confirm.agent.id)}>
              {confirm.action === "delete" ? "Delete Agent" : "Stop Agent"}
            </Button>
          </div>
        )}
      >
        {null}
      </Dialog>
    </div>
  );
}
