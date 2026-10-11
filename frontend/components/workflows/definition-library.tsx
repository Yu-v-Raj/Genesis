"use client";

import { useCallback, useEffect, useState } from "react";
import { BookCopy, LoaderCircle, Play } from "lucide-react";

import { WorkflowApiError, WorkflowService } from "@/services/workflow.service";
import type { StoredWorkflowDefinition, Workflow } from "@/types/workflows";

/** Saved workflow definitions. Each run snapshots the latest version when it is created. */
export function DefinitionLibrary({ refreshKey, onRunStarted }: { refreshKey: number; onRunStarted: (run: Workflow) => void }) {
  const [definitions, setDefinitions] = useState<StoredWorkflowDefinition[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setDefinitions((await WorkflowService.definitions()).definitions);
    } catch (cause) {
      setError(cause instanceof WorkflowApiError ? cause.message : "Unable to load workflow definitions.");
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void load());
  }, [load, refreshKey]);

  async function run(definition: StoredWorkflowDefinition) {
    if (starting) return;
    setStarting(definition.definition_id);
    setError(null);
    try {
      onRunStarted(await WorkflowService.runDefinition(definition.definition_id));
    } catch (cause) {
      setError(cause instanceof WorkflowApiError ? cause.message : "The run could not be started.");
    } finally {
      setStarting(null);
    }
  }

  return (
    <section aria-labelledby="definition-library-title" className="rounded-xl border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <h2 id="definition-library-title" className="text-sm font-semibold text-foreground">Saved workflows</h2>
          <p className="mt-1 text-xs text-muted-foreground">Reusable plans. Starting one creates a new run; editing a plan never changes runs already created.</p>
        </div>
        <BookCopy className="h-4 w-4 text-primary" aria-hidden="true" />
      </div>
      {error && (
        <p role="alert" className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-400/25 bg-red-400/5 px-3 py-2 text-xs text-red-200">
          {error}
          <button type="button" onClick={() => void load()} className="rounded border border-red-300/30 px-2 py-0.5 font-medium hover:bg-red-300/10">Retry</button>
        </p>
      )}
      {definitions === null && !error ? (
        <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />Loading…</p>
      ) : definitions !== null && definitions.length === 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">No saved workflows yet. Creating a workflow also saves it here.</p>
      ) : (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {definitions?.map((definition) => (
            <li key={definition.definition_id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
              <span className="min-w-0">
                <span className="block truncate text-sm font-medium text-foreground">{definition.name}</span>
                <span className="text-[11px] text-muted-foreground">v{definition.version} · {definition.tasks.length} step{definition.tasks.length === 1 ? "" : "s"}</span>
              </span>
              <button
                type="button"
                onClick={() => void run(definition)}
                disabled={starting !== null}
                aria-label={`Run ${definition.name}`}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {starting === definition.definition_id ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Play className="h-3.5 w-3.5" aria-hidden="true" />}
                Run
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
