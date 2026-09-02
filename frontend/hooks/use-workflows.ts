"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RealtimeState } from "@/hooks/use-realtime";
import { WorkflowApiError, WorkflowService } from "@/services/workflow.service";
import type { Workflow, WorkflowCreateRequest, WorkflowHistoryItem, WorkflowTask } from "@/types/workflows";
import type { RealtimeEvent } from "@/types/realtime";

const WORKFLOW_EVENTS = new Set(["workflow.created", "workflow.queued", "workflow.started", "workflow.paused", "workflow.resumed", "workflow.completed", "workflow.failed", "workflow.cancelled", "workflow.task.ready", "workflow.task.started", "workflow.task.completed", "workflow.task.failed"]);
const workflowIdFromEvent = (event: RealtimeEvent) => typeof event.payload.workflow_id === "string" ? event.payload.workflow_id : null;
const message = (error: unknown) => error instanceof WorkflowApiError ? error.message : "The Workflow Runtime request could not be completed.";
const upsert = (workflows: Workflow[], workflow: Workflow) => [workflow, ...workflows.filter((item) => item.workflow_id !== workflow.workflow_id)];
const historyFromTasks = (tasks: WorkflowTask[]): WorkflowHistoryItem[] => tasks.map((task): WorkflowHistoryItem => ({ id: `${task.task_id}-${task.finished_at ?? task.started_at ?? task.created_at}`, event: "task", timestamp: task.finished_at ?? task.started_at ?? task.created_at, workflow_id: task.workflow_id, task_id: task.task_id, task_name: task.name, status: task.status, result: task.result, error: task.error })).sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));

export interface WorkflowsState {
  workflows: Workflow[]; selectedWorkflow: Workflow | null; tasks: WorkflowTask[]; history: WorkflowHistoryItem[];
  loading: boolean; detailsLoading: boolean; error: string | null; pendingWorkflowIds: ReadonlySet<string>; latestWorkflowEvent: RealtimeEvent | null;
  selectWorkflow: (workflowId: string | null) => Promise<void>; create: (input: WorkflowCreateRequest) => Promise<Workflow | null>;
  remove: (workflowId: string) => Promise<boolean>; lifecycle: (workflowId: string, action: "start" | "pause" | "resume" | "cancel") => Promise<Workflow | null>; retry: () => Promise<void>;
}

/** Reconciles REST snapshots with the one shared Genesis realtime connection. */
export function useWorkflows(realtime: RealtimeState): WorkflowsState {
  const [workflows, setWorkflows] = useState<Workflow[]>([]); const [selectedWorkflow, setSelectedWorkflow] = useState<Workflow | null>(null);
  const [tasks, setTasks] = useState<WorkflowTask[]>([]); const [history, setHistory] = useState<WorkflowHistoryItem[]>([]);
  const [loading, setLoading] = useState(true); const [detailsLoading, setDetailsLoading] = useState(false); const [error, setError] = useState<string | null>(null); const [pendingWorkflowIds, setPendingWorkflowIds] = useState<Set<string>>(new Set());
  const latestWorkflowEvent = realtime.latestEvent && WORKFLOW_EVENTS.has(realtime.latestEvent.event_type) && workflowIdFromEvent(realtime.latestEvent) ? realtime.latestEvent : null;
  const load = useCallback(async () => { setLoading(true); setError(null); try { const result = await WorkflowService.list(); setWorkflows(result.workflows); setSelectedWorkflow((current) => current ? result.workflows.find((item) => item.workflow_id === current.workflow_id) ?? null : null); } catch (caught) { setError(message(caught)); } finally { setLoading(false); } }, []);
  const selectWorkflow = useCallback(async (workflowId: string | null) => { if (!workflowId) { setSelectedWorkflow(null); setTasks([]); setHistory([]); return; } setDetailsLoading(true); setError(null); try { const [workflow, taskResponse, historyResponse] = await Promise.all([WorkflowService.get(workflowId), WorkflowService.tasks(workflowId), WorkflowService.history(workflowId)]); setSelectedWorkflow(workflow); setTasks(taskResponse.tasks); setHistory(historyFromTasks(historyResponse.tasks)); setWorkflows((current) => upsert(current, workflow)); } catch (caught) { setError(message(caught)); } finally { setDetailsLoading(false); } }, []);
  useEffect(() => { queueMicrotask(() => void load()); }, [load]);
  useEffect(() => { if (!latestWorkflowEvent) return; const workflowId = workflowIdFromEvent(latestWorkflowEvent); if (!workflowId) return; void WorkflowService.get(workflowId).then((workflow) => { setWorkflows((current) => upsert(current, workflow)); if (selectedWorkflow?.workflow_id === workflowId) { setSelectedWorkflow(workflow); setTasks(workflow.tasks); setHistory(historyFromTasks(workflow.tasks)); } }).catch(() => undefined); }, [latestWorkflowEvent, selectedWorkflow?.workflow_id]);
  const create = useCallback(async (input: WorkflowCreateRequest) => { setError(null); try { const workflow = await WorkflowService.create(input); setWorkflows((current) => upsert(current, workflow)); await selectWorkflow(workflow.workflow_id); return workflow; } catch (caught) { setError(message(caught)); return null; } }, [selectWorkflow]);
  const remove = useCallback(async (workflowId: string) => { setPendingWorkflowIds((current) => new Set(current).add(workflowId)); setError(null); try { await WorkflowService.delete(workflowId); setWorkflows((current) => current.filter((item) => item.workflow_id !== workflowId)); if (selectedWorkflow?.workflow_id === workflowId) await selectWorkflow(null); return true; } catch (caught) { setError(message(caught)); return false; } finally { setPendingWorkflowIds((current) => { const next = new Set(current); next.delete(workflowId); return next; }); } }, [selectWorkflow, selectedWorkflow]);
  const lifecycle = useCallback(async (workflowId: string, action: "start" | "pause" | "resume" | "cancel") => { setPendingWorkflowIds((current) => new Set(current).add(workflowId)); setError(null); try { const workflow = await WorkflowService[action](workflowId); setWorkflows((current) => upsert(current, workflow)); if (selectedWorkflow?.workflow_id === workflowId) { setSelectedWorkflow(workflow); setTasks(workflow.tasks); setHistory(historyFromTasks(workflow.tasks)); } return workflow; } catch (caught) { setError(message(caught)); return null; } finally { setPendingWorkflowIds((current) => { const next = new Set(current); next.delete(workflowId); return next; }); } }, [selectedWorkflow]);
  return { workflows, selectedWorkflow, tasks, history, loading, detailsLoading, error, pendingWorkflowIds: useMemo(() => pendingWorkflowIds, [pendingWorkflowIds]), latestWorkflowEvent, selectWorkflow, create, remove, lifecycle, retry: load };
}
