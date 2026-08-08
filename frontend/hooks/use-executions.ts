"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { RealtimeState } from "@/hooks/use-realtime";
import { ExecutionApiError, ExecutionService } from "@/services/execution.service";
import type { Execution } from "@/types/executions";
import type { RealtimeEvent } from "@/types/realtime";

const EXECUTION_EVENT_PREFIX = "execution.";

function executionIdFromEvent(event: RealtimeEvent): string | null {
  const executionId = event.payload.execution_id;
  return typeof executionId === "string" ? executionId : null;
}

function isExecutionEvent(event: RealtimeEvent): boolean {
  return event.event_type.startsWith(EXECUTION_EVENT_PREFIX) && executionIdFromEvent(event) !== null;
}

function upsertExecution(executions: Execution[], updated: Execution): Execution[] {
  const withoutUpdated = executions.filter((execution) => execution.execution_id !== updated.execution_id);
  return [updated, ...withoutUpdated].sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
  );
}

function messageFor(error: unknown): string {
  return error instanceof ExecutionApiError
    ? error.message
    : "The Execution Runtime request could not be completed.";
}

export interface ExecutionsState {
  executions: Execution[];
  loading: boolean;
  error: string | null;
  pendingExecutionIds: ReadonlySet<string>;
  pendingAgentIds: ReadonlySet<string>;
  latestExecutionEvent: RealtimeEvent | null;
  executeAgent: (agentId: string) => Promise<boolean>;
  cancelExecution: (executionId: string) => Promise<boolean>;
  loadAgentExecutions: (agentId: string) => Promise<void>;
  retry: () => Promise<void>;
}

/** Coordinates REST execution snapshots with the shared Genesis WebSocket stream. */
export function useExecutions(realtime: RealtimeState): ExecutionsState {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingExecutionIds, setPendingExecutionIds] = useState<Set<string>>(new Set());
  const [pendingAgentIds, setPendingAgentIds] = useState<Set<string>>(new Set());
  const { latestEvent } = realtime;
  const latestExecutionEvent = latestEvent !== null && isExecutionEvent(latestEvent) ? latestEvent : null;

  const loadExecutions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await ExecutionService.list();
      setExecutions(result.executions);
    } catch (caughtError) {
      setError(messageFor(caughtError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => void loadExecutions());
  }, [loadExecutions]);

  useEffect(() => {
    if (latestExecutionEvent === null) return;
    const executionId = executionIdFromEvent(latestExecutionEvent);
    if (executionId === null) return;
    void ExecutionService.get(executionId)
      .then((execution) => setExecutions((current) => upsertExecution(current, execution)))
      .catch(() => undefined);
  }, [latestExecutionEvent]);

  const executeAgent = useCallback(async (agentId: string): Promise<boolean> => {
    setPendingAgentIds((current) => new Set(current).add(agentId));
    setError(null);
    try {
      const execution = await ExecutionService.execute(agentId);
      setExecutions((current) => upsertExecution(current, execution));
      return true;
    } catch (caughtError) {
      setError(messageFor(caughtError));
      return false;
    } finally {
      setPendingAgentIds((current) => {
        const next = new Set(current);
        next.delete(agentId);
        return next;
      });
    }
  }, []);

  const cancelExecution = useCallback(async (executionId: string): Promise<boolean> => {
    setPendingExecutionIds((current) => new Set(current).add(executionId));
    setError(null);
    try {
      const execution = await ExecutionService.cancel(executionId);
      setExecutions((current) => upsertExecution(current, execution));
      return true;
    } catch (caughtError) {
      setError(messageFor(caughtError));
      return false;
    } finally {
      setPendingExecutionIds((current) => {
        const next = new Set(current);
        next.delete(executionId);
        return next;
      });
    }
  }, []);

  const loadAgentExecutions = useCallback(async (agentId: string): Promise<void> => {
    try {
      const result = await ExecutionService.listForAgent(agentId);
      setExecutions((current) => {
        const otherAgents = current.filter((execution) => execution.agent_id !== agentId);
        return [...result.executions, ...otherAgents].sort(
          (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
        );
      });
    } catch (caughtError) {
      setError(messageFor(caughtError));
    }
  }, []);

  return {
    executions,
    loading,
    error,
    pendingExecutionIds: useMemo(() => pendingExecutionIds, [pendingExecutionIds]),
    pendingAgentIds: useMemo(() => pendingAgentIds, [pendingAgentIds]),
    latestExecutionEvent,
    executeAgent,
    cancelExecution,
    loadAgentExecutions,
    retry: loadExecutions,
  };
}
