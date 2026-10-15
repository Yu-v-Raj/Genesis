"use client";

import Link from "next/link";
import { ChevronRight, ShieldAlert, Wrench } from "lucide-react";

import { JsonView } from "@/components/ui/disclosure";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatDuration } from "@/lib/operations";
import { toolLabel } from "@/lib/tools";
import { cn } from "@/lib/utils";
import { dependencyNames, stepArguments, stepDuration, stepStages, stepToolName } from "@/lib/workflows";
import type { ToolDefinition } from "@/types/tools";
import type { WorkflowTask } from "@/types/workflows";

/** A step as defined (saved workflow) or as it ran (a run's own copy, with status and times). */
export type StepItem = {
  task_id: string;
  name: string;
  dependencies: string[];
  configuration: Record<string, unknown>;
} & Partial<Pick<WorkflowTask, "status" | "started_at" | "finished_at" | "result" | "error">>;

function time(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleTimeString() : "—";
}

/**
 * Steps grouped by their declared dependencies. Steps in one stage can run at the same
 * time; every step names what it waits for. Results and errors are untrusted data,
 * shown as escaped text and collapsed until opened.
 */
export function StepList({ steps, tools }: { steps: readonly StepItem[]; tools: ReadonlyMap<string, ToolDefinition> }) {
  const stages = stepStages(steps);
  return (
    <ol className="flex flex-col gap-4" aria-label="Steps">
      {stages.map((stage, index) => (
        <li key={index} className="flex flex-col gap-2">
          {stages.length > 1 && (
            <p className="text-[11px] font-medium uppercase tracking-wider text-subtle">
              Stage {index + 1}{stage.length > 1 ? " · these can run at the same time" : ""}
            </p>
          )}
          <ul className="flex flex-col gap-2">
            {stage.map((step) => <StepRow key={step.task_id} step={step} steps={steps} tool={tools.get(stepToolName(step) ?? "")} />)}
          </ul>
        </li>
      ))}
    </ol>
  );
}

function StepRow({ step, steps, tool }: { step: StepItem; steps: readonly StepItem[]; tool: ToolDefinition | undefined }) {
  const toolName = stepToolName(step);
  const waitsFor = dependencyNames(step, steps);
  const duration = step.status ? stepDuration({ started_at: step.started_at ?? null, finished_at: step.finished_at ?? null }) : null;
  const hasResult = step.result !== undefined && step.result !== null;
  const args = stepArguments(step);

  return (
    <li className="rounded-md border border-border bg-surface-2/40">
      <details className="group/step">
        <summary className="flex cursor-pointer list-none items-start gap-3 px-3 py-2.5 [&::-webkit-details-marker]:hidden">
          <Wrench aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1">
            <span className="block break-words text-sm text-foreground">{step.name}</span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
              <span>{toolName ? toolLabel(toolName) : "Unknown tool"}</span>
              <span aria-hidden>·</span>
              <span>{waitsFor.length ? `after ${waitsFor.join(", ")}` : "starts right away"}</span>
              {tool?.side_effects && <span className="inline-flex items-center gap-1 text-warning"><ShieldAlert aria-hidden className="h-3 w-3" />may change things outside Genesis</span>}
              {step.status && (step.started_at || step.finished_at) && (
                <><span aria-hidden>·</span><span>{time(step.started_at)} → {time(step.finished_at)}{duration !== null ? ` (${formatDuration(duration)})` : ""}</span></>
              )}
            </span>
          </span>
          {step.status && <StatusBadge status={step.status} className="shrink-0" />}
          <ChevronRight aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open/step:rotate-90" />
        </summary>
        <div className="flex flex-col gap-3 border-t border-border px-3 py-3 text-xs">
          {step.error && <p className="break-words rounded-md border tone-danger tone-border tone-bg px-2.5 py-2 text-foreground">{step.error}</p>}
          {hasResult && <div><p className="mb-1 text-muted-foreground">Result</p><JsonView value={step.result} className="max-h-48" /></div>}
          {step.status && !hasResult && !step.error && <p className="text-muted-foreground">{step.status === "completed" ? "Completed with no output." : "No result recorded yet."}</p>}
          <div><p className="mb-1 text-muted-foreground">Arguments</p>{Object.keys(args).length ? <JsonView value={args} className="max-h-40" /> : <p className="text-foreground">None</p>}</div>
          <p className="flex flex-wrap items-center gap-x-2 text-[11px] text-subtle">
            <span>Step ID <code className="font-mono text-foreground/80">{step.task_id}</code></span>
            {toolName && <><span aria-hidden>·</span><Link href={`/tools?tool=${encodeURIComponent(toolName)}`} className={cn("hover:text-foreground")}>About the {toolLabel(toolName).toLowerCase()} tool</Link></>}
          </p>
        </div>
      </details>
    </li>
  );
}
