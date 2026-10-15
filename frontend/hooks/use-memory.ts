"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { RealtimeState } from "@/hooks/use-realtime";
import { MemoryApiError, MemoryService } from "@/services/memory.service";
import type { CreateMemoryInput, MemoryRecord, UpdateMemoryInput } from "@/types/memory";

const CHANGE_EVENTS = new Set(["memory.created", "memory.updated", "memory.deleted"]);

const newestFirst = (memories: MemoryRecord[]) =>
  [...memories].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));

function errorMessage(error: unknown): string {
  return error instanceof MemoryApiError ? error.message : "The Memory Runtime request could not be completed.";
}

/** Which Agent and search the loaded records answer. */
export interface MemoryView {
  agentId: string;
  query: string;
}

export type MutationResult = { record: MemoryRecord; error: null } | { record: null; error: string };

export interface MemoryState {
  /** Records for `view`; empty until a request has succeeded. */
  records: MemoryRecord[];
  /** What `records` belongs to, or `null` before the first successful load. */
  view: MemoryView | null;
  loading: boolean;
  /** The latest list/search failure for the requested Agent and query. */
  error: string | null;
  pendingIds: ReadonlySet<string>;
  create: (agentId: string, input: CreateMemoryInput) => Promise<MutationResult>;
  update: (memoryId: string, input: UpdateMemoryInput) => Promise<MutationResult>;
  remove: (memoryId: string) => Promise<{ ok: boolean; error: string | null }>;
  reload: () => void;
}

/**
 * One Agent's memories (optionally narrowed by the server's text search), kept current
 * with realtime events. Responses for a previous Agent or query are discarded, so records
 * can never appear under the wrong Agent while switching.
 */
export function useMemory(agentId: string | null, query: string, realtime: RealtimeState): MemoryState {
  const [records, setRecords] = useState<MemoryRecord[]>([]);
  const [view, setView] = useState<MemoryView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());
  const [reloadToken, setReloadToken] = useState(0);
  const requestSeq = useRef(0);
  const trimmed = query.trim();

  useEffect(() => {
    const seq = ++requestSeq.current;
    queueMicrotask(() => {
      if (seq !== requestSeq.current) return;
      if (agentId === null) {
        setRecords([]);
        setView(null);
        setError(null);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      (trimmed ? MemoryService.search(agentId, trimmed) : MemoryService.listForAgent(agentId))
        .then((result) => {
          if (seq !== requestSeq.current) return;
          setRecords(newestFirst(result.memories.filter((memory) => memory.agent_id === agentId)));
          setView({ agentId, query: trimmed });
        })
        .catch((cause) => {
          if (seq !== requestSeq.current) return;
          setError(errorMessage(cause));
        })
        .finally(() => {
          if (seq === requestSeq.current) setLoading(false);
        });
    });
  }, [agentId, trimmed, reloadToken]);

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  // Changes made elsewhere (another tab, or the API) arrive as events; re-run the current
  // list or search so filtering stays the server's. Retrieval events change nothing.
  useEffect(() => {
    const event = realtime.latestEvent;
    if (event === null || !CHANGE_EVENTS.has(event.event_type)) return;
    if (event.payload.agent_id !== agentId) return;
    queueMicrotask(reload);
  }, [realtime.latestEvent, agentId, reload]);

  const track = useCallback((memoryId: string, busy: boolean) => {
    setPendingIds((current) => {
      const next = new Set(current);
      if (busy) next.add(memoryId); else next.delete(memoryId);
      return next;
    });
  }, []);

  const create = useCallback(async (targetAgentId: string, input: CreateMemoryInput): Promise<MutationResult> => {
    try {
      const record = await MemoryService.create(targetAgentId, input);
      reload();
      return { record, error: null };
    } catch (cause) {
      return { record: null, error: errorMessage(cause) };
    }
  }, [reload]);

  const update = useCallback(async (memoryId: string, input: UpdateMemoryInput): Promise<MutationResult> => {
    track(memoryId, true);
    try {
      const record = await MemoryService.update(memoryId, input);
      setRecords((current) => current.map((memory) => (memory.memory_id === memoryId ? record : memory)));
      reload();
      return { record, error: null };
    } catch (cause) {
      return { record: null, error: errorMessage(cause) };
    } finally {
      track(memoryId, false);
    }
  }, [reload, track]);

  const remove = useCallback(async (memoryId: string) => {
    track(memoryId, true);
    try {
      await MemoryService.delete(memoryId);
      setRecords((current) => current.filter((memory) => memory.memory_id !== memoryId));
      reload();
      return { ok: true, error: null };
    } catch (cause) {
      return { ok: false, error: errorMessage(cause) };
    } finally {
      track(memoryId, false);
    }
  }, [reload, track]);

  return { records, view, loading, error, pendingIds, create, update, remove, reload };
}
