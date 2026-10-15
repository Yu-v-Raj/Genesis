import type { EventListResponse } from "@/types/agents";

const EVENT_API_BASE_URL =
  process.env.NEXT_PUBLIC_EVENT_API_BASE_URL ?? "http://127.0.0.1:8000/api";

/** Read-only adapter for the existing bounded Genesis event history. */
export const EventHistoryService = Object.freeze({
  /** Newest first. The backend accepts 1–1000 and keeps a bounded in-memory history. */
  recent: async (limit = 100): Promise<EventListResponse> => {
    const response = await fetch(`${EVENT_API_BASE_URL}/events?limit=${Math.min(Math.max(Math.trunc(limit), 1), 1000)}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Unable to load lifecycle history.");
    return response.json() as Promise<EventListResponse>;
  },
});
