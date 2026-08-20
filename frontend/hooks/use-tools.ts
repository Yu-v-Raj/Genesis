"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RealtimeState } from "@/hooks/use-realtime";
import { ToolApiError, ToolService } from "@/services/tool.service";
import type { ToolDefinition, ToolTask } from "@/types/tools";
import type { RealtimeEvent } from "@/types/realtime";

const TOOL_EVENTS = new Set(["tool.executed", "tool.completed", "tool.failed", "task.created", "task.completed", "task.failed"]);
const time = (task: ToolTask) => new Date(task.finished_at ?? task.started_at ?? 0).getTime();
const sortTasks = (tasks: ToolTask[]) => [...tasks].sort((a, b) => time(b) - time(a));
const message = (error: unknown) => error instanceof ToolApiError ? error.message : "The Tool Runtime request could not be completed.";

export interface ToolsState {
  tools: ToolDefinition[]; tasks: ToolTask[]; capabilities: string[]; loading: boolean; error: string | null;
  pendingToolNames: ReadonlySet<string>; latestToolEvent: RealtimeEvent | null;
  execute: (toolName: string, arguments_: Record<string, unknown>) => Promise<ToolTask | null>; retry: () => Promise<void>;
}

/** Merges Tool Runtime REST snapshots with the shared Genesis realtime stream. */
export function useTools(realtime: RealtimeState): ToolsState {
  const [tools, setTools] = useState<ToolDefinition[]>([]); const [tasks, setTasks] = useState<ToolTask[]>([]);
  const [capabilities, setCapabilities] = useState<string[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  const [pendingToolNames, setPendingToolNames] = useState<Set<string>>(new Set());
  const latestToolEvent = realtime.latestEvent && TOOL_EVENTS.has(realtime.latestEvent.event_type) ? realtime.latestEvent : null;
  const load = useCallback(async () => { setLoading(true); setError(null); try { const [listed, history, caps] = await Promise.all([ToolService.list(), ToolService.history(), ToolService.capabilities()]); setTools(listed.tools); setTasks(sortTasks(history.tasks)); setCapabilities(caps.capabilities); } catch (caught) { setError(message(caught)); } finally { setLoading(false); } }, []);
  useEffect(() => { queueMicrotask(() => void load()); }, [load]);
  useEffect(() => { if (!latestToolEvent) return; void ToolService.history().then(({ tasks: next }) => setTasks(sortTasks(next))).catch(() => undefined); }, [latestToolEvent]);
  const execute = useCallback(async (toolName: string, arguments_: Record<string, unknown>) => { setPendingToolNames(current => new Set(current).add(toolName)); setError(null); try { const task = await ToolService.execute({ tool_name: toolName, arguments: arguments_ }); setTasks(current => sortTasks([task, ...current.filter(item => item.task_id !== task.task_id)])); return task; } catch (caught) { setError(message(caught)); return null; } finally { setPendingToolNames(current => { const next = new Set(current); next.delete(toolName); return next; }); } }, []);
  return { tools, tasks, capabilities, loading, error, pendingToolNames: useMemo(() => pendingToolNames, [pendingToolNames]), latestToolEvent, execute, retry: load };
}
