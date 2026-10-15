"use client";

import Link from "next/link";
import { ArrowLeft, Play, ShieldAlert } from "lucide-react";

import { StepList } from "@/components/workflows/step-list";
import { Button, IconButton } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Disclosure, JsonView } from "@/components/ui/disclosure";
import { StatusBadge } from "@/components/ui/status-badge";
import { relativeTime } from "@/lib/operations";
import { toolLabel } from "@/lib/tools";
import { runProgress, toolsUsed } from "@/lib/workflows";
import type { ToolDefinition } from "@/types/tools";
import type { StoredWorkflowDefinition, Workflow } from "@/types/workflows";

/** A saved workflow: what it does, its steps and tools, its runs, and an explicit Run. */
export function DefinitionView({ definition, runs, tools, now, pending, onRun, onOpenRun, onBack }: {
  definition: StoredWorkflowDefinition;
  runs: readonly Workflow[];
  tools: ReadonlyMap<string, ToolDefinition>;
  now: Date;
  pending: boolean;
  onRun: () => void;
  onOpenRun: (runId: string) => void;
  onBack: () => void;
}) {
  const used = toolsUsed(definition.tasks);
  const missing = used.filter((name) => !tools.has(name));
  const disabled = used.filter((name) => tools.get(name)?.enabled === false);
  const external = used.filter((name) => tools.get(name)?.side_effects);
  const runnable = missing.length === 0 && disabled.length === 0;

  return (
    <article aria-labelledby="definition-title" className="flex min-w-0 flex-col gap-4">
      <header className="flex items-start gap-2">
        <IconButton label="Back" onClick={onBack} className="-ml-1 lg:hidden"><ArrowLeft aria-hidden className="h-4 w-4" /></IconButton>
        <div className="min-w-0 flex-1">
          <h2 id="definition-title" className="break-words text-base font-semibold text-foreground">{definition.name}</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{definition.description || "No description."}</p>
          <p className="mt-1 text-xs text-subtle">Version {definition.version} · saved {relativeTime(definition.created_at, now)} · {definition.tasks.length} step{definition.tasks.length === 1 ? "" : "s"}</p>
        </div>
        <Button variant="primary" size="sm" onClick={onRun} loading={pending} disabled={!runnable} icon={<Play aria-hidden className="h-3.5 w-3.5" />} className="shrink-0">Run…</Button>
      </header>

      {!runnable && (
        <p role="note" className="text-xs text-warning">
          {missing.length ? `Uses tools the server doesn't have: ${missing.join(", ")}. ` : ""}{disabled.length ? `Uses disabled tools: ${disabled.join(", ")}.` : ""} The server would fail those steps, so running is disabled here.
        </p>
      )}

      <section className="flex flex-col gap-2 border-t border-border pt-4" aria-label="Tools used">
        <h3 className="text-xs font-medium uppercase tracking-wider text-subtle">Uses</h3>
        <ul className="flex flex-wrap gap-2">
          {used.map((name) => (
            <li key={name}><Link href={`/tools?tool=${encodeURIComponent(name)}`} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-2 px-2 py-1 text-xs text-foreground hover:border-border-strong">{toolLabel(name)}{tools.get(name)?.side_effects && <ShieldAlert aria-label="may change things outside Genesis" className="h-3 w-3 text-warning" />}</Link></li>
          ))}
        </ul>
        <p className="text-[11px] leading-4 text-subtle">
          Steps call these tools directly on the server, in the order below. No Agent or model is involved{external.length ? `; ${external.map(toolLabel).join(", ")} may change things outside Genesis` : ""}.
        </p>
      </section>

      <section aria-label="Steps" className="flex flex-col gap-2 border-t border-border pt-4">
        <h3 className="text-xs font-medium uppercase tracking-wider text-subtle">Steps</h3>
        <StepList steps={definition.tasks} tools={tools} />
      </section>

      <section aria-label="Runs" className="flex flex-col gap-2 border-t border-border pt-4">
        <h3 className="text-xs font-medium uppercase tracking-wider text-subtle">Runs{runs.length ? ` (${runs.length})` : ""}</h3>
        {runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">Not run yet.</p>
        ) : (
          <ul className="divide-y divide-border rounded-md border border-border">
            {runs.slice(0, 10).map((run) => {
              const progress = runProgress(run);
              return (
                <li key={run.workflow_id}>
                  <button type="button" onClick={() => onOpenRun(run.workflow_id)} className="flex w-full items-center gap-3 px-3 py-2 text-left text-xs hover:bg-white/[0.025]">
                    <span className="min-w-0 flex-1 text-muted-foreground">v{run.definition_version ?? "?"}{run.attempt > 1 ? ` · attempt ${run.attempt}` : ""} · {progress.completed}/{progress.total} steps</span>
                    <time dateTime={run.created_at} className="shrink-0 text-[11px] text-subtle">{relativeTime(run.created_at, now)}</time>
                    <StatusBadge status={run.status} className="shrink-0" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <Disclosure summary="Technical details">
        <dl className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
          <dt className="text-muted-foreground">Workflow ID</dt>
          <dd className="flex min-w-0 items-center gap-1"><span className="truncate font-mono text-[11px] text-foreground">{definition.definition_id}</span><CopyButton value={definition.definition_id} label="Copy workflow ID" /></dd>
          <dt className="text-muted-foreground">Version</dt><dd className="font-mono text-foreground">{definition.version}</dd>
          <dt className="text-muted-foreground">Metadata</dt><dd>{Object.keys(definition.metadata).length ? <JsonView value={definition.metadata} /> : <span className="text-foreground">None</span>}</dd>
        </dl>
      </Disclosure>
    </article>
  );
}
