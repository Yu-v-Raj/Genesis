"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RealtimeState } from "@/hooks/use-realtime";
import { WorkflowApiError, WorkflowService } from "@/services/workflow.service";
import type { StoredWorkflowDefinition, Workflow, WorkflowCreateRequest } from "@/types/workflows";

const message = (error: unknown) => (error instanceof WorkflowApiError ? error.message : "The Workflow Runtime request could not be completed.");

export type RunResult = { run: Workflow; error: null } | { run: null; error: string };
export type LifecycleAction = "start" | "pause" | "resume" | "cancel";

export interface WorkflowsState {
  definitions: StoredWorkflowDefinition[];
  runs: Workflow[];
  /** `false` until both lists have loaded once, so an empty list is never shown by mistake. */
  loaded: boolean;
  loading: boolean;
  error: string | null;
  pendingIds: ReadonlySet<string>;
  reload: () => Promise<void>;
  /** Saves a workflow and creates its first run (not started), as the API does. */
  create: (input: WorkflowCreateRequest) => Promise<RunResult>;
  /** Creates and queues a run of the latest version of a saved workflow. */
  runDefinition: (definitionId: string) => Promise<RunResult>;
  lifecycle: (runId: string, action: LifecycleAction) => Promise<RunResult>;
  retry: (runId: string, acknowledgeSideEffects: boolean) => Promise<RunResult>;
  remove: (runId: string) => Promise<{ ok: boolean; error: string | null }>;
}

const upsert = (runs: Workflow[], run: Workflow) => [run, ...runs.filter((item) => item.workflow_id !== run.workflow_id)];

/**
 * Saved workflows and runs from the Workflow Runtime, kept current by `workflow.*` events on
 * the page's one shared realtime connection. Every state shown comes from the server.
 */
export function useWorkflows(realtime: RealtimeState): WorkflowsState {
  const [definitions, setDefinitions] = useState<StoredWorkflowDefinition[]>([]);
  const [runs, setRuns] = useState<Workflow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [definitionList, runList] = await Promise.all([WorkflowService.definitions(), WorkflowService.list()]);
      setDefinitions(definitionList.definitions);
      setRuns(runList.workflows);
      setLoaded(true);
    } catch (cause) {
      setError(message(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void reload()); }, [reload]);

  useEffect(() => {
    const event = realtime.latestEvent;
    if (!event || !event.event_type.startsWith("workflow.")) return;
    if (event.event_type.startsWith("workflow.definition.")) {
      void WorkflowService.definitions().then((list) => setDefinitions(list.definitions)).catch(() => undefined);
      return;
    }
    const runId = typeof event.payload.workflow_id === "string" ? event.payload.workflow_id : null;
    if (!runId) return;
    void WorkflowService.get(runId)
      .then((run) => setRuns((current) => upsert(current, run)))
      .catch((cause) => {
        if (cause instanceof WorkflowApiError && cause.status === 404) setRuns((current) => current.filter((run) => run.workflow_id !== runId));
      });
  }, [realtime.latestEvent]);

  const track = useCallback((id: string, busy: boolean) => {
    setPendingIds((current) => {
      const next = new Set(current);
      if (busy) next.add(id); else next.delete(id);
      return next;
    });
  }, []);

  const guarded = useCallback(async (id: string, work: () => Promise<Workflow>): Promise<RunResult> => {
    track(id, true);
    try {
      const run = await work();
      setRuns((current) => upsert(current, run));
      return { run, error: null };
    } catch (cause) {
      return { run: null, error: message(cause) };
    } finally {
      track(id, false);
    }
  }, [track]);

  const create = useCallback(async (input: WorkflowCreateRequest) => {
    const result = await guarded("create", () => WorkflowService.create(input));
    if (result.run) void WorkflowService.definitions().then((list) => setDefinitions(list.definitions)).catch(() => undefined);
    return result;
  }, [guarded]);

  const runDefinition = useCallback((definitionId: string) => guarded(definitionId, () => WorkflowService.runDefinition(definitionId)), [guarded]);
  const lifecycle = useCallback((runId: string, action: LifecycleAction) => guarded(runId, () => WorkflowService[action](runId)), [guarded]);
  const retry = useCallback((runId: string, acknowledge: boolean) => guarded(runId, () => WorkflowService.retry(runId, acknowledge)), [guarded]);

  const remove = useCallback(async (runId: string) => {
    track(runId, true);
    try {
      await WorkflowService.delete(runId);
      setRuns((current) => current.filter((run) => run.workflow_id !== runId));
      return { ok: true, error: null };
    } catch (cause) {
      return { ok: false, error: message(cause) };
    } finally {
      track(runId, false);
    }
  }, [track]);

  return { definitions, runs, loaded, loading, error, pendingIds: useMemo(() => pendingIds, [pendingIds]), reload, create, runDefinition, lifecycle, retry, remove };
}
