"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useReducedMotion } from "framer-motion";
import { Activity, ArrowLeft, BrainCircuit, ChevronDown, CirclePlay, CircleStop, Info, MessageSquarePlus, MoreHorizontal, Settings2, Trash2, X } from "lucide-react";

import { AgentAvatar } from "@/components/agents/agent-avatar";
import { Composer } from "@/components/agents/composer";
import { LiveTurn, SavedTurn, UnfinishedTurn } from "@/components/agents/conversation-turn";
import { Button, IconButton, buttonClasses } from "@/components/ui/button";
import { Alert, Skeleton } from "@/components/ui/feedback";
import { Menu, type MenuEntry } from "@/components/ui/menu";
import { StatusBadge } from "@/components/ui/status-badge";
import type { useAgentConversation } from "@/hooks/use-agent-conversation";
import { canEditSettings, lifecycleActionsFor, liveTurnSteps, type LifecycleAction } from "@/lib/agent-directory";
import { groupTurns, modelLabel, type AgentReadiness } from "@/lib/agent-experience";
import { operationsQuery, relativeTime } from "@/lib/operations";
import { cn } from "@/lib/utils";
import type { Agent } from "@/types/agents";
import type { Execution } from "@/types/executions";

const SETTINGS_FIXES = new Set(["needs-model", "model-unavailable", "provider-unconfigured"]);

/** Starter prompts only for tools this Agent may actually use; each fills the message box. */
function starterPrompts(agent: Agent): string[] {
  const prompts = ["What can you help me with?"];
  if (agent.allowed_tools.includes("calculator")) prompts.push("What is 18% of 2,450? Use the calculator.");
  if (agent.allowed_tools.includes("random_number")) prompts.push("Pick a random number between 1 and 100.");
  if (agent.allowed_tools.includes("uuid")) prompts.push("Generate a new UUID for me.");
  return prompts.slice(0, 3);
}

export interface AgentWorkspaceProps {
  agent: Agent;
  readiness: AgentReadiness | null;
  conversation: ReturnType<typeof useAgentConversation>;
  /** The live execution of the turn in flight, from the page's realtime execution state. */
  liveExecution: Execution | null;
  cancelling: boolean;
  onCancelRun: (executionId: string) => void;
  onConfigure: () => void;
  onInitialize: () => void;
  onOpenDetails: () => void;
  onAction: (action: LifecycleAction) => void;
  lifecyclePending: boolean;
  onBack: () => void;
}

/** The selected Agent: header, conversation, live progress and the message box. */
export function AgentWorkspace({ agent, readiness, conversation, liveExecution, cancelling, onCancelRun, onConfigure, onInitialize, onOpenDetails, onAction, lifecyclePending, onBack }: AgentWorkspaceProps) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const reduceMotion = useReducedMotion();
  const router = useRouter();
  // Never show another Agent's data while a switch is still loading.
  const own = conversation.sessionAgentId === null || conversation.sessionAgentId === agent.id;
  const { switching, pendingMessage, problem, loadError } = conversation;
  const messages = own ? conversation.messages : [];
  const sessionId = own ? conversation.sessionId : null;
  const sessions = conversation.sessions.filter((item) => item.agent_id === agent.id);
  const unfinished = own ? conversation.unfinished.filter((execution) => execution.agent_id === agent.id) : [];
  const executions = conversation.executions.filter((execution) => execution.agent_id === agent.id);
  // Until a conversation has loaded, show loading rather than an empty welcome that would
  // wrongly suggest the Agent has no history.
  const loading = conversation.loading || !own || (conversation.sessionId === null && !loadError);
  const pending = pendingMessage !== null;
  const turns = groupTurns(messages);
  const executionsById = new Map(executions.map((execution) => [execution.execution_id, execution]));
  // A turn in flight: sent from this box (pending), or a run already underway, such as a retry.
  const liveMessage = pending ? pendingMessage : liveExecution && typeof liveExecution.metadata.message === "string" ? liveExecution.metadata.message : null;
  const steps = liveMessage !== null ? liveTurnSteps(liveExecution) : [];
  const canChat = readiness?.canChat === true;
  const disabledReason = canChat ? null : readiness?.detail ?? "Loading…";
  const actions = lifecycleActionsFor(agent.status);
  const now = new Date();

  // Follow new content only while the reader is already at the bottom.
  useEffect(() => {
    const log = logRef.current;
    if (log && stickToBottom.current) log.scrollTo({ top: log.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
  }, [turns.length, liveMessage, steps.length, problem, unfinished.length, reduceMotion]);

  async function send() {
    const text = input.trim();
    if (!text || !canChat || pending) return;
    setInput("");
    stickToBottom.current = true;
    const response = await conversation.send(text);
    // Keep what was typed if the send failed and nothing new was entered meanwhile.
    if (response === null) setInput((current) => current || text);
    inputRef.current?.focus();
  }

  function fillPrompt(prompt: string) {
    setInput(prompt);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  const currentSession = sessions.find((item) => item.id === sessionId);
  const sessionItems: MenuEntry[] = sessions.map((item) => ({
    key: item.id,
    label: item.title ?? (item.message_count === 0 ? "New conversation" : "Conversation"),
    description: `${item.message_count} message${item.message_count === 1 ? "" : "s"} · ${relativeTime(item.updated_at, now)}`,
    checked: item.id === sessionId,
    disabled: pending || switching,
    onSelect: () => void conversation.openSession(item.id),
  }));
  const newDisabled = pending || switching || agent.status === "stopped" || (messages.length === 0 && sessionId !== null);

  const moreItems: MenuEntry[] = [
    { key: "details", label: "Agent details", description: "Runs, runtime context and lifecycle", icon: <Info />, onSelect: onOpenDetails },
    { key: "settings", label: "Settings", icon: <Settings2 />, onSelect: onConfigure, disabled: !canEditSettings(agent.status) },
    { key: "memory", label: "View memory", description: "What this Agent remembers", icon: <BrainCircuit />, onSelect: () => router.push(`/memory?agent=${agent.id}`) },
    { key: "runs", label: "View runs in Operations", icon: <Activity />, onSelect: () => router.push(`/monitoring${operationsQuery({ agentId: agent.id })}`) },
  ];
  if (actions.length) moreItems.push("separator");
  if (actions.includes("initialize")) moreItems.push({ key: "initialize", label: "Finish setup", icon: <CirclePlay />, onSelect: () => onAction("initialize"), disabled: lifecyclePending });
  if (actions.includes("stop")) moreItems.push({ key: "stop", label: "Stop Agent", description: "It can no longer chat", icon: <CircleStop />, onSelect: () => onAction("stop"), disabled: lifecyclePending || pending });
  if (actions.includes("delete")) moreItems.push({ key: "delete", label: "Delete…", icon: <Trash2 />, onSelect: () => onAction("delete"), disabled: lifecyclePending, danger: true });

  return (
    <section aria-labelledby="workspace-agent-name" className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
      <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-border px-3 py-2.5 sm:px-5">
        <IconButton label="Back to Agents" onClick={onBack} className="-ml-1 lg:hidden"><ArrowLeft aria-hidden className="h-4 w-4" /></IconButton>
        <AgentAvatar name={agent.name} />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <h2 id="workspace-agent-name" className="min-w-0 truncate text-sm font-semibold text-foreground" title={agent.name}>{agent.name}</h2>
            <StatusBadge status={agent.status} className="shrink-0" />
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {agent.llm_model ? modelLabel(agent.llm_model) : "No model selected"}
            {" · "}
            {agent.allowed_tools.length === 0 ? "No tools" : `${agent.allowed_tools.length} tool${agent.allowed_tools.length === 1 ? "" : "s"}`}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Menu
            heading="Conversations"
            triggerLabel={`Switch conversation (current: ${currentSession?.title ?? "new conversation"})`}
            items={sessionItems}
            width="w-72"
            trigger={<><span className="hidden max-w-40 truncate md:inline">{currentSession?.title ?? (sessionId ? "Current conversation" : "Conversations")}</span><span className="md:hidden">History</span><ChevronDown aria-hidden className="h-3.5 w-3.5" /></>}
            triggerClassName={cn(buttonClasses("ghost", "sm"), "max-w-56")}
          />
          <Button size="sm" variant="secondary" onClick={() => void conversation.startNewConversation()} disabled={newDisabled} loading={switching}
            title={messages.length === 0 && sessionId !== null ? "This conversation is already empty" : "Start a new conversation"}
            icon={<MessageSquarePlus aria-hidden className="h-3.5 w-3.5" />}>
            <span className="hidden sm:inline">New conversation</span><span className="sm:hidden">New</span>
          </Button>
          <IconButton label="Agent settings" onClick={onConfigure} disabled={!canEditSettings(agent.status)}><Settings2 aria-hidden className="h-4 w-4" /></IconButton>
          <Menu triggerLabel={`More actions for ${agent.name}`} items={moreItems} trigger={<MoreHorizontal aria-hidden className="h-4 w-4" />}
            triggerClassName="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-white/[0.05] hover:text-foreground" />
        </div>
      </header>

      <div
        ref={logRef}
        onScroll={(event) => { const { scrollTop, scrollHeight, clientHeight } = event.currentTarget; stickToBottom.current = scrollHeight - scrollTop - clientHeight < 80; }}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6 sm:px-6">
          {readiness && !readiness.canChat && readiness.state !== "working" && (
            <Alert tone="warning" action={
              SETTINGS_FIXES.has(readiness.state) ? <Button size="sm" onClick={onConfigure}>Open settings</Button>
              : readiness.state === "not-initialized" ? <Button size="sm" onClick={onInitialize} loading={lifecyclePending}>Finish setup</Button>
              : undefined}>
              {readiness.detail}
            </Alert>
          )}
          {readiness?.state === "provider-unconfigured" && <Alert tone="warning">{readiness.detail}</Alert>}
          {loadError && <Alert tone="danger" action={<Button size="sm" onClick={() => void conversation.reload()}>Try again</Button>}>{loadError}</Alert>}

          {loading && turns.length === 0 && !loadError ? (
            <div className="flex flex-col gap-6" aria-busy="true" aria-label="Loading conversation">
              <Skeleton className="ml-auto h-9 w-2/5" /><Skeleton className="h-16 w-3/4" /><Skeleton className="ml-auto h-9 w-1/3" />
            </div>
          ) : turns.length === 0 && liveMessage === null && unfinished.length === 0 && !loadError ? (
            <div className="flex flex-col items-start gap-4 py-8 sm:py-14">
              <AgentAvatar name={agent.name} size="lg" />
              <div>
                <p className="text-lg font-semibold tracking-tight text-foreground">Start a conversation with {agent.name}</p>
                <p className="mt-1 max-w-lg text-sm leading-6 text-muted-foreground">{agent.description || "Ask a question or describe a task."} Type below to begin.</p>
              </div>
              {canChat && (
                <div className="flex flex-wrap gap-2" aria-label="Example messages">
                  {starterPrompts(agent).map((prompt) => (
                    <button key={prompt} type="button" onClick={() => fillPrompt(prompt)} className="rounded-md border border-border bg-surface px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground">
                      {prompt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div role="log" aria-label={`Conversation with ${agent.name}`} aria-live="polite" aria-relevant="additions" className="flex flex-col gap-6">
              {turns.map((turn) => <SavedTurn key={turn.id} turn={turn} agentName={agent.name} execution={executionsById.get(turn.id)} />)}
            </div>
          )}

          {liveMessage !== null && (
            <LiveTurn message={liveMessage} agentName={agent.name} steps={steps} execution={liveExecution} cancelling={cancelling}
              onCancel={liveExecution ? () => onCancelRun(liveExecution.execution_id) : null} />
          )}

          {!pending && unfinished.map((execution) => (
            <UnfinishedTurn key={execution.execution_id} execution={execution} onRetry={(acknowledge) => conversation.retryUnfinished(execution.execution_id, acknowledge)} />
          ))}

          {problem && (
            <Alert tone="danger" action={
              <div className="flex gap-1">
                {problem.configure && <Button size="sm" onClick={onConfigure}>Open settings</Button>}
                <IconButton label="Dismiss" onClick={conversation.dismissProblem}><X aria-hidden className="h-3.5 w-3.5" /></IconButton>
              </div>}>
              <p className="font-medium">{problem.title}</p>
              <p className="mt-0.5 break-words text-xs leading-5 text-muted-foreground">{problem.message}</p>
            </Alert>
          )}
        </div>
      </div>

      <div className="shrink-0 border-t border-border bg-background/60 px-3 pb-3 pt-3 sm:px-5">
        <Composer value={input} onChange={setInput} onSubmit={() => void send()} inputRef={inputRef} agentName={agent.name} disabledReason={disabledReason} pending={pending} />
      </div>
      <p className="sr-only" role="status">{liveMessage !== null ? `${agent.name} is working on your message.` : ""}</p>
    </section>
  );
}
