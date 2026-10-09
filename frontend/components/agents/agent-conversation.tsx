"use client";

import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  AlertTriangle, Bot, CheckCircle2, CircleStop, LoaderCircle, Send, Settings2, ShieldX, Wrench, X, XCircle,
} from "lucide-react";

import {
  formatToolValue, groupTurns, modelLabel, toolStepLabel,
  type AgentReadiness, type ChatProblem, type ToolStep,
} from "@/lib/agent-experience";
import type { Agent, SessionMessage } from "@/types/agents";

interface AgentConversationProps {
  agent: Agent | null;
  readiness: AgentReadiness | null;
  messages: SessionMessage[];
  pendingMessage: string | null;
  problem: ChatProblem | null;
  loadError: string | null;
  onSend: (message: string) => Promise<unknown>;
  onConfigure: () => void;
  onInitialize: () => void;
  onDismissProblem: () => void;
}

const SETTINGS_FIXES = new Set(["needs-model", "model-unavailable", "provider-unconfigured"]);

export function ReadinessBadge({ readiness }: { readiness: AgentReadiness }) {
  const tone = readiness.state === "ready"
    ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-200"
    : readiness.state === "working"
      ? "border-primary/30 bg-primary/10 text-blue-200"
      : readiness.state === "stopped"
        ? "border-slate-400/25 bg-slate-400/10 text-slate-200"
        : "border-amber-400/25 bg-amber-400/10 text-amber-200";
  const Icon = readiness.state === "ready" ? CheckCircle2 : readiness.state === "working" ? LoaderCircle : readiness.state === "stopped" ? CircleStop : AlertTriangle;
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${tone}`}>
      <Icon className={`h-3 w-3 ${readiness.state === "working" ? "animate-spin" : ""}`} aria-hidden="true" />
      {readiness.label}
    </span>
  );
}

function ToolStepRow({ step }: { step: ToolStep }) {
  const Icon = step.status === "completed" ? CheckCircle2 : step.status === "rejected" ? ShieldX : XCircle;
  const tone = step.status === "completed" ? "text-emerald-300" : step.status === "rejected" ? "text-amber-300" : "text-red-300";
  return (
    <details className="group rounded-lg border border-border bg-background/40 text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-muted-foreground">
        <Wrench className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        <span>Used <span className="font-medium text-foreground">{step.name.replaceAll("_", " ")}</span></span>
        <span className={`ml-auto inline-flex items-center gap-1 ${tone}`}><Icon className="h-3.5 w-3.5" aria-hidden="true" />{toolStepLabel(step)}</span>
      </summary>
      <div className="border-t border-border px-3 py-2 font-mono text-[11px] leading-5 text-foreground/85">
        {step.status === "completed" ? <>Result: {formatToolValue(step.result)}</> : <>Reason: {step.error ?? "Unknown"}</>}
      </div>
    </details>
  );
}

function Bubble({ role, children }: { role: "user" | "assistant"; children: React.ReactNode }) {
  return (
    <div className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-sm leading-6 ${role === "user" ? "ml-auto rounded-br-md bg-primary text-white" : "rounded-bl-md border border-border bg-background text-foreground"}`}>
      <span className="sr-only">{role === "user" ? "You: " : "Agent: "}</span>
      {children}
    </div>
  );
}

export function AgentConversation({
  agent, readiness, messages, pendingMessage, problem, loadError, onSend, onConfigure, onInitialize, onDismissProblem,
}: AgentConversationProps) {
  const [input, setInput] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  const turns = groupTurns(messages);
  const pending = pendingMessage !== null;
  const canSend = agent !== null && readiness?.canChat === true && !pending;

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, pendingMessage, problem]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = input.trim();
    if (!text || !canSend) return;
    setInput("");
    const response = await onSend(text);
    if (response === null) setInput((current) => current || text);
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  }

  if (agent === null) {
    return (
      <section className="flex min-h-80 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface p-8 text-center">
        <Bot className="h-7 w-7 text-primary" aria-hidden="true" />
        <p className="mt-3 text-sm text-muted-foreground">Select an Agent to start a conversation.</p>
      </section>
    );
  }

  const suggestion = agent.allowed_tools.includes("calculator") ? "Calculate 25 * 4" : "What can you help me with?";

  return (
    <section aria-label={`Conversation with ${agent.name}`} className="flex min-h-[28rem] min-w-0 flex-col rounded-xl border border-border bg-surface shadow-sm lg:h-[calc(100vh-12rem)]">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-base font-semibold text-foreground">{agent.name}</h2>
            {readiness && <ReadinessBadge readiness={readiness} />}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {agent.llm_model ? modelLabel(agent.llm_model) : "No model selected"}
            {" · "}
            {agent.allowed_tools.length === 0 ? "No tools" : `Tools: ${agent.allowed_tools.map((tool) => tool.replaceAll("_", " ")).join(", ")}`}
          </p>
        </div>
        <button type="button" onClick={onConfigure} disabled={agent.status === "running" || agent.status === "stopped"} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50">
          <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />Settings
        </button>
      </header>

      {readiness && !readiness.canChat && readiness.state !== "working" && (
        <div role="status" className="mx-4 mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2.5 text-sm text-amber-100">
          <span>{readiness.detail}</span>
          {SETTINGS_FIXES.has(readiness.state) && <button type="button" onClick={onConfigure} className="rounded-md border border-amber-300/30 px-2.5 py-1 text-xs font-medium hover:bg-amber-300/10">Open settings</button>}
          {readiness.state === "not-initialized" && <button type="button" onClick={onInitialize} className="rounded-md border border-amber-300/30 px-2.5 py-1 text-xs font-medium hover:bg-amber-300/10">Finish setup</button>}
        </div>
      )}
      {readiness?.state === "provider-unconfigured" && (
        <p role="note" className="mx-4 mt-4 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs text-amber-100">{readiness.detail}</p>
      )}

      <div ref={logRef} role="log" aria-live="polite" aria-relevant="additions" className="flex-1 space-y-4 overflow-y-auto p-4">
        {loadError && <p role="alert" className="text-sm text-red-200">{loadError}</p>}
        {turns.length === 0 && !pending ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-10 text-center">
            <p className="text-sm text-muted-foreground">No messages yet.</p>
            {readiness?.canChat && (
              <button type="button" onClick={() => setInput(suggestion)} className="rounded-full border border-border px-3 py-1.5 text-xs text-foreground hover:bg-white/[0.05]">
                Try “{suggestion}”
              </button>
            )}
          </div>
        ) : (
          turns.map((turn) => (
            <div key={turn.id} className="space-y-2">
              {turn.user !== null && <Bubble role="user">{turn.user}</Bubble>}
              {turn.tools.length > 0 && <div className="max-w-[85%] space-y-1.5">{turn.tools.map((step, index) => <ToolStepRow key={`${turn.id}-${index}`} step={step} />)}</div>}
              {turn.reply !== null && <Bubble role="assistant">{turn.reply}</Bubble>}
            </div>
          ))
        )}
        {pending && (
          <div className="space-y-2">
            <Bubble role="user">{pendingMessage}</Bubble>
            <p className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />{agent.name} is working… tool use will appear with the reply.</p>
          </div>
        )}
      </div>

      {problem && (
        <div role="alert" className="mx-4 mb-3 flex items-start gap-3 rounded-lg border border-red-400/25 bg-red-400/5 p-3 text-sm text-red-100">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="font-medium">{problem.title}</p>
            <p className="mt-0.5 break-words text-xs text-red-200/90">{problem.message}</p>
            {problem.configure && <button type="button" onClick={onConfigure} className="mt-2 rounded-md border border-red-300/30 px-2.5 py-1 text-xs font-medium hover:bg-red-300/10">Open settings</button>}
          </div>
          <button type="button" onClick={onDismissProblem} className="rounded p-1 text-red-200 hover:bg-red-300/10" aria-label="Dismiss error"><X className="h-3.5 w-3.5" /></button>
        </div>
      )}

      <form onSubmit={submit} className="flex items-end gap-2 border-t border-border p-3">
        <label htmlFor="agent-composer" className="sr-only">Message {agent.name}</label>
        <textarea
          id="agent-composer"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onComposerKeyDown}
          disabled={!canSend}
          rows={1}
          placeholder={readiness?.canChat ? `Message ${agent.name}… (Enter to send, Shift+Enter for a new line)` : readiness?.detail ?? "Loading…"}
          className="max-h-40 min-h-10 min-w-0 flex-1 resize-y rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground/70 focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-60"
        />
        <button type="submit" disabled={!canSend || !input.trim()} aria-label="Send message" className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-primary px-3 text-sm font-medium text-white transition-colors hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-50">
          {pending ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
          <span className="hidden sm:inline">{pending ? "Sending" : "Send"}</span>
        </button>
      </form>
    </section>
  );
}
