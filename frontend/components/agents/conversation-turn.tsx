"use client";

import Link from "next/link";
import { ArrowUpRight, CheckCircle2, ChevronRight, LoaderCircle, ShieldX, Square, Wrench, XCircle } from "lucide-react";

import { AgentAvatar } from "@/components/agents/agent-avatar";
import { RetryControl } from "@/components/durable/retry-control";
import { Button } from "@/components/ui/button";
import { JsonView } from "@/components/ui/disclosure";
import { Markdown } from "@/components/ui/markdown";
import { StatusBadge } from "@/components/ui/status-badge";
import type { LiveStep } from "@/lib/agent-directory";
import { toolStepLabel, type ConversationTurn, type ToolStep } from "@/lib/agent-experience";
import { statusText } from "@/lib/durable-work";
import { errorCategoryLabel, formatDuration, operationsQuery } from "@/lib/operations";
import { cn } from "@/lib/utils";
import type { Execution } from "@/types/executions";

const runHref = (executionId: string) => `/monitoring${operationsQuery({ execution: executionId })}`;

function RunLink({ executionId, label = "Run details" }: { executionId: string; label?: string }) {
  return (
    <Link href={runHref(executionId)} className="inline-flex items-center gap-0.5 rounded text-muted-foreground transition-colors hover:text-foreground">
      {label}<ArrowUpRight aria-hidden className="h-3 w-3" />
      <span className="sr-only"> (opens in Operations)</span>
    </Link>
  );
}

export function UserMessage({ children }: { children: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-lg rounded-br-sm border border-border bg-surface-2 px-3.5 py-2 text-sm leading-6 text-foreground sm:max-w-[75%]">
        <span className="sr-only">You: </span>{children}
      </div>
    </div>
  );
}

/** A recorded tool call from the saved conversation. Results stay collapsed until asked for. */
function ToolStepRow({ step }: { step: ToolStep }) {
  const Icon = step.status === "completed" ? CheckCircle2 : step.status === "rejected" ? ShieldX : XCircle;
  const tone = step.status === "completed" ? "text-success" : step.status === "rejected" ? "text-warning" : "text-danger";
  const hasDetail = step.status === "completed" ? step.result !== null && step.result !== undefined : Boolean(step.error);
  return (
    <details className="group/tool rounded-md border border-border bg-surface/60 text-xs">
      <summary className={cn("flex list-none items-center gap-2 px-3 py-2 text-muted-foreground [&::-webkit-details-marker]:hidden", hasDetail ? "cursor-pointer hover:text-foreground" : "cursor-default")}>
        <Wrench aria-hidden className="h-3.5 w-3.5 shrink-0" />
        <span className="min-w-0 truncate">Used <span className="font-medium text-foreground">{step.name.replaceAll("_", " ")}</span></span>
        <span className={cn("ml-auto inline-flex shrink-0 items-center gap-1", tone)}><Icon aria-hidden className="h-3.5 w-3.5" />{toolStepLabel(step)}</span>
        {hasDetail && <ChevronRight aria-hidden className="h-3.5 w-3.5 shrink-0 transition-transform group-open/tool:rotate-90" />}
      </summary>
      {hasDetail && (
        <div className="border-t border-border p-2">
          {step.status === "completed" ? <JsonView value={step.result} className="max-h-48" /> : <p className="break-words px-1 text-danger">{step.error}</p>}
        </div>
      )}
    </details>
  );
}

function AgentReply({ agentName, children }: { agentName: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <AgentAvatar name={agentName} size="sm" className="mt-0.5" />
      <div className="min-w-0 flex-1">
        <span className="sr-only">{agentName}: </span>
        {children}
      </div>
    </div>
  );
}

/** One saved turn: the message, any tool calls, the reply, and its run outcome when known. */
export function SavedTurn({ turn, agentName, execution }: { turn: ConversationTurn; agentName: string; execution: Execution | undefined }) {
  const executionId = turn.id.startsWith("message-") ? null : turn.id;
  return (
    <article className="flex flex-col gap-3">
      {turn.user !== null && <UserMessage>{turn.user}</UserMessage>}
      {(turn.tools.length > 0 || turn.reply !== null) && (
        <AgentReply agentName={agentName}>
          {turn.tools.length > 0 && <div className="mb-3 flex flex-col gap-1.5" aria-label="Tool activity">{turn.tools.map((step, index) => <ToolStepRow key={index} step={step} />)}</div>}
          {turn.reply !== null && <Markdown source={turn.reply} />}
          {executionId && (
            <p className="mt-2 flex flex-wrap items-center gap-x-2 text-[11px] text-subtle">
              {execution && <span>{execution.status === "completed" ? "Completed" : statusText(execution.status)}{execution.duration !== null ? ` in ${formatDuration(execution.duration)}` : ""}</span>}
              {execution && <span aria-hidden>·</span>}
              <RunLink executionId={executionId} />
            </p>
          )}
        </AgentReply>
      )}
    </article>
  );
}

/**
 * The turn in flight: the message, then progress taken from its live execution record.
 * Nothing is shown as the reply until the saved reply arrives.
 */
export function LiveTurn({ message, agentName, steps, execution, cancelling, onCancel }: {
  message: string; agentName: string; steps: LiveStep[]; execution: Execution | null; cancelling: boolean; onCancel: (() => void) | null;
}) {
  return (
    <article className="flex flex-col gap-3" aria-busy="true">
      <UserMessage>{message}</UserMessage>
      <AgentReply agentName={agentName}>
        <ol className="flex flex-col gap-1.5" aria-label={`${agentName}'s progress`}>
          {steps.map((step, index) => (
            <li key={`${step.label}-${index}`} className="flex items-center gap-2 text-xs">
              {step.state === "active"
                ? <LoaderCircle aria-hidden className="h-3.5 w-3.5 animate-spin text-accent-2" />
                : <CheckCircle2 aria-hidden className="h-3.5 w-3.5 text-muted-foreground" />}
              <span className={step.state === "active" ? "text-foreground" : "text-muted-foreground"}>{step.label}</span>
            </li>
          ))}
        </ol>
        {execution && (
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle">
            <RunLink executionId={execution.execution_id} label="Follow in Operations" />
            {onCancel && (
              <Button size="sm" variant="ghost" onClick={onCancel} loading={cancelling} icon={<Square aria-hidden className="h-3 w-3" />} className="h-7 px-2 text-xs">
                {cancelling ? "Cancelling…" : "Cancel"}
              </Button>
            )}
          </p>
        )}
      </AgentReply>
    </article>
  );
}

/** A message whose turn failed, was cancelled or interrupted: shown with the server's retry decision. */
export function UnfinishedTurn({ execution, onRetry }: { execution: Execution; onRetry: (acknowledgeSideEffects: boolean) => Promise<string | null> }) {
  const message = typeof execution.metadata.message === "string" ? execution.metadata.message : "";
  const category = errorCategoryLabel(execution.error_category);
  return (
    <article className="flex flex-col gap-3" aria-label="Message that didn't finish">
      {message && <UserMessage>{message}</UserMessage>}
      <div className="ml-10 flex flex-col gap-2 rounded-md border tone-danger tone-border bg-surface p-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={execution.status} />
          <span className="text-foreground">This message didn&apos;t get a reply{category ? ` — ${category.toLowerCase()}` : ""}.</span>
        </div>
        {execution.error && <p className="break-words leading-5 text-muted-foreground">{execution.error}</p>}
        <p className="text-[11px] text-subtle"><RunLink executionId={execution.execution_id} /></p>
        <RetryControl retry={execution.retry} onRetry={onRetry} />
      </div>
    </article>
  );
}
