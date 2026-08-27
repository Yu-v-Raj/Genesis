export type MemoryKind = "fact" | "note" | "preference" | "context";

export interface MemoryRecord {
  memory_id: string;
  agent_id: string;
  content: string;
  kind: MemoryKind;
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
  tags: string[];
}

export interface MemoryListResponse {
  memories: MemoryRecord[];
}

export interface CreateMemoryInput {
  content: string;
  kind: MemoryKind;
  metadata: Record<string, unknown>;
  tags: string[];
}

export interface UpdateMemoryInput {
  content?: string;
  kind?: MemoryKind;
  metadata?: Record<string, unknown>;
  tags?: string[];
}
