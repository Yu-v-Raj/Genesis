"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RealtimeState } from "@/hooks/use-realtime";
import { ToolApiError, ToolService } from "@/services/tool.service";
import type { ToolDefinition, ToolTask } from "@/types/tools";
import type { RealtimeEvent } from "@/types/realtime";

const TOOL_EVENTS = new Set(["tool.executed", "tool.completed", "tool.failed", "task.created", "task.completed", "task.failed"]);
const PAGE = 100;
const time = (task: ToolTask) => new Date(task.created_at ?? task.started_at ?? task.finished_at ?? 0).getTime();
const sortTasks = (tasks: ToolTask[]) => [...tasks].sort((a, b) => time(b) - time(a));
/** Newer copies of a task replace older ones; newest first. */
const mergeTasks = (current: ToolTask[], incoming: ToolTask[]) => {
  const byId = new Map(current.map((task) => [task.task_id, task]));
  for (const task of incoming) byId.set(task.task_id, task);
  return sortTasks([...byId.values()]);
};
const message = (error: unknown) => (error instanceof ToolApiError ? error.message : "The Tool Runtime request could not be completed.");

export type TestRunResult =
  | { task: ToolTask; error: null; approvalId?: undefined }
  | { task: null; error: string; approvalId?: undefined }
  /** Held for the operator's decision; nothing ran. */
  | { task: null; error: null; approvalId: string; detail: string };

export interface ToolsState {
  tools: ToolDefinition[];
  tasks: ToolTask[];
  capabilities: string[];
  loading: boolean;
  /** The latest failure to load tools or history. */
  error: string | null;
  pendingToolNames: ReadonlySet<string>;
  latestToolEvent: RealtimeEvent | null;
  /** More runs are stored than are loaded; `loadOlder` fetches the next page. */
  hasOlder: boolean;
  loadingOlder: boolean;
  loadOlder: () => Promise<void>;
  /** An operator test run through the server's Tool Runtime; only called from an explicit action. */
  execute: (toolName: string, arguments_: Record<string, unknown>) => Promise<TestRunResult>;
  retry: () => Promise<void>;
}

/** Merges Tool Runtime REST snapshots with the shared Genesis realtime stream. */
export function useTools(realtime: RealtimeState): ToolsState {
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [tasks, setTasks] = useState<ToolTask[]>([]);
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingToolNames, setPendingToolNames] = useState<Set<string>>(new Set());
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const latestToolEvent = realtime.latestEvent && TOOL_EVENTS.has(realtime.latestEvent.event_type) ? realtime.latestEvent : null;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listed, history, caps] = await Promise.all([ToolService.list(), ToolService.history({ limit: PAGE }), ToolService.capabilities()]);
      setTools(listed.tools);
      setTasks(sortTasks(history.tasks));
      setNextBefore(history.next_before ?? null);
      setCapabilities(caps.capabilities);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  useEffect(() => {
    if (!latestToolEvent) return;
    void ToolService.history({ limit: PAGE }).then(({ tasks: next }) => setTasks((current) => mergeTasks(current, next))).catch(() => undefined);
  }, [latestToolEvent]);

  const loadOlder = useCallback(async () => {
    if (!nextBefore) return;
    setLoadingOlder(true);
    try {
      const page = await ToolService.history({ limit: PAGE, before: nextBefore });
      setTasks((current) => mergeTasks(current, page.tasks));
      setNextBefore(page.next_before ?? null);
    } catch (caught) {
      setError(message(caught));
    } finally {
      setLoadingOlder(false);
    }
  }, [nextBefore]);

  const execute = useCallback(async (toolName: string, arguments_: Record<string, unknown>): Promise<TestRunResult> => {
    setPendingToolNames((current) => new Set(current).add(toolName));
    try {
      const response = await ToolService.execute({ tool_name: toolName, arguments: arguments_ });
      if ("approval_id" in response) return { task: null, error: null, approvalId: response.approval_id, detail: response.detail };
      const task = response;
      setTasks((current) => mergeTasks(current, [task]));
      return { task, error: null };
    } catch (caught) {
      // A rejected run is still recorded by the server; refresh so it appears in history.
      void ToolService.history({ limit: PAGE }).then(({ tasks: next }) => setTasks((current) => mergeTasks(current, next))).catch(() => undefined);
      return { task: null, error: message(caught) };
    } finally {
      setPendingToolNames((current) => {
        const next = new Set(current);
        next.delete(toolName);
        return next;
      });
    }
  }, []);

  return {
    tools, tasks, capabilities, loading, error, pendingToolNames: useMemo(() => pendingToolNames, [pendingToolNames]), latestToolEvent,
    hasOlder: nextBefore !== null, loadingOlder, loadOlder, execute, retry: load,
  };
}
