"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { RealtimeState } from "@/hooks/use-realtime";
import { MemoryApiError, MemoryService } from "@/services/memory.service";
import type { CreateMemoryInput, MemoryRecord, UpdateMemoryInput } from "@/types/memory";
import type { RealtimeEvent } from "@/types/realtime";

const MEMORY_EVENTS = new Set(["memory.created", "memory.updated", "memory.deleted", "memory.retrieved"]);

const newestFirst = (memories: MemoryRecord[]) =>
  [...memories].sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at));

function eventId(event: RealtimeEvent, key: "memory_id" | "agent_id"): string | null {
  const value = event.payload[key];
  return typeof value === "string" ? value : null;
}

function errorMessage(error: unknown): string {
  return error instanceof MemoryApiError ? error.message : "The Memory Runtime request could not be completed.";
}

export interface MemoryState {
  memories: MemoryRecord[];
  loading: boolean;
  searching: boolean;
  error: string | null;
  pendingMemoryIds: ReadonlySet<string>;
  create: (agentId: string, input: CreateMemoryInput) => Promise<MemoryRecord | null>;
  update: (memoryId: string, input: UpdateMemoryInput) => Promise<MemoryRecord | null>;
  remove: (memoryId: string) => Promise<boolean>;
  search: (agentId: string, query: string) => Promise<void>;
  load: (agentId: string) => Promise<void>;
}

/** Synchronizes scoped Memory Runtime snapshots with the existing real-time stream. */
export function useMemory(selectedAgentId: string | null, realtime: RealtimeState): MemoryState {
  const [memories, setMemories] = useState<MemoryRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingMemoryIds, setPendingMemoryIds] = useState<Set<string>>(new Set());

  const load = useCallback(async (agentId: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await MemoryService.listForAgent(agentId);
      setMemories(newestFirst(result.memories));
    } catch (caughtError) {
      setError(errorMessage(caughtError));
      setMemories([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedAgentId === null) {
      setMemories([]);
      setError(null);
      setLoading(false);
      return;
    }
    queueMicrotask(() => void load(selectedAgentId));
  }, [load, selectedAgentId]);

  useEffect(() => {
    const event = realtime.latestEvent;
    if (event === null || !MEMORY_EVENTS.has(event.event_type)) return;
    const agentId = eventId(event, "agent_id");
    const memoryId = eventId(event, "memory_id");
    if (agentId !== selectedAgentId || memoryId === null) return;

    // GET /api/memory/{id} emits memory.retrieved. Fetching again for that
    // informational event would publish another retrieval event indefinitely.
    // It carries no changed record data, so the current local snapshot is valid.
    if (event.event_type === "memory.retrieved") return;

    if (event.event_type === "memory.deleted") {
      setMemories((current) => current.filter((memory) => memory.memory_id !== memoryId));
      return;
    }
    void MemoryService.get(memoryId)
      .then((record) => setMemories((current) => newestFirst([
        record,
        ...current.filter((memory) => memory.memory_id !== record.memory_id),
      ])))
      .catch(() => undefined);
  }, [realtime.latestEvent, selectedAgentId]);

  const create = useCallback(async (agentId: string, input: CreateMemoryInput) => {
    setError(null);
    try {
      const record = await MemoryService.create(agentId, input);
      if (agentId === selectedAgentId) {
        setMemories((current) => newestFirst([record, ...current]));
      }
      return record;
    } catch (caughtError) {
      setError(errorMessage(caughtError));
      return null;
    }
  }, [selectedAgentId]);

  const update = useCallback(async (memoryId: string, input: UpdateMemoryInput) => {
    setPendingMemoryIds((current) => new Set(current).add(memoryId));
    setError(null);
    try {
      const record = await MemoryService.update(memoryId, input);
      setMemories((current) => newestFirst(current.map((memory) => memory.memory_id === memoryId ? record : memory)));
      return record;
    } catch (caughtError) {
      setError(errorMessage(caughtError));
      return null;
    } finally {
      setPendingMemoryIds((current) => {
        const next = new Set(current);
        next.delete(memoryId);
        return next;
      });
    }
  }, []);

  const remove = useCallback(async (memoryId: string) => {
    setPendingMemoryIds((current) => new Set(current).add(memoryId));
    setError(null);
    try {
      await MemoryService.delete(memoryId);
      setMemories((current) => current.filter((memory) => memory.memory_id !== memoryId));
      return true;
    } catch (caughtError) {
      setError(errorMessage(caughtError));
      return false;
    } finally {
      setPendingMemoryIds((current) => {
        const next = new Set(current);
        next.delete(memoryId);
        return next;
      });
    }
  }, []);

  const search = useCallback(async (agentId: string, query: string) => {
    setSearching(true);
    setError(null);
    try {
      const result = await MemoryService.search(agentId, query);
      setMemories(newestFirst(result.memories));
    } catch (caughtError) {
      setError(errorMessage(caughtError));
      setMemories([]);
    } finally {
      setSearching(false);
    }
  }, []);

  return { memories, loading, searching, error, pendingMemoryIds: useMemo(() => pendingMemoryIds, [pendingMemoryIds]), create, update, remove, search, load };
}
