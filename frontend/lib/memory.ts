/**
 * Pure view logic for the Memory library: kinds, form parsing and validation (mirroring the
 * server's rules), kind filters and summaries. Free of React for `node --test`.
 */
import type { CreateMemoryInput, MemoryKind, MemoryRecord } from "@/types/memory";

/** The server limit for memory content (MemoryCreateRequest: 1–10,000 characters). */
export const MAX_CONTENT = 10_000;
export const DEFAULT_KIND: MemoryKind = "note";

export const MEMORY_KINDS: readonly { value: MemoryKind; label: string; description: string }[] = [
  { value: "fact", label: "Fact", description: "Something true, such as a name, number or decision." },
  { value: "note", label: "Note", description: "General information worth keeping." },
  { value: "preference", label: "Preference", description: "How someone likes things done." },
  { value: "context", label: "Context", description: "Background about a project or situation." },
];

export function kindLabel(kind: string): string {
  return MEMORY_KINDS.find((item) => item.value === kind)?.label ?? kind;
}

/** Comma-separated tags, trimmed, without blanks or duplicates (unchanged behaviour). */
export function parseTags(value: string): string[] {
  return [...new Set(value.split(",").map((tag) => tag.trim()).filter(Boolean))];
}

export function metadataText(metadata: Record<string, unknown>): string {
  return Object.keys(metadata).length === 0 ? "" : JSON.stringify(metadata, null, 2);
}

/** A JSON object, or `{}` when blank; `null` when the text isn't a JSON object. */
export function parseMetadata(value: string): Record<string, unknown> | null {
  if (!value.trim()) return {};
  try {
    const parsed: unknown = JSON.parse(value);
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export interface MemoryDraft {
  content: string;
  kind: MemoryKind;
  tags: string;
  metadata: string;
}

export function draftFrom(record?: MemoryRecord | null): MemoryDraft {
  return record
    ? { content: record.content, kind: record.kind, tags: record.tags.join(", "), metadata: metadataText(record.metadata) }
    : { content: "", kind: DEFAULT_KIND, tags: "", metadata: "" };
}

export type DraftErrors = Partial<Record<"content" | "metadata", string>>;

/** Validate a draft and build the request payload, or explain what to fix. */
export function validateDraft(draft: MemoryDraft): { input: CreateMemoryInput; errors: null } | { input: null; errors: DraftErrors } {
  const errors: DraftErrors = {};
  const content = draft.content.trim();
  if (!content) errors.content = "Write what this Agent should remember.";
  else if (content.length > MAX_CONTENT) errors.content = `Keep it under ${MAX_CONTENT.toLocaleString("en-US")} characters (currently ${content.length.toLocaleString("en-US")}).`;
  const metadata = parseMetadata(draft.metadata);
  if (metadata === null) errors.metadata = "Metadata must be a JSON object, for example {\"source\": \"operator\"}.";
  if (Object.keys(errors).length > 0 || metadata === null) return { input: null, errors };
  return { input: { content, kind: draft.kind, tags: parseTags(draft.tags), metadata }, errors: null };
}

/** Whether the draft differs from what it was opened with (ignoring tag spacing). */
export function isDraftDirty(draft: MemoryDraft, initial: MemoryDraft): boolean {
  return draft.content !== initial.content
    || draft.kind !== initial.kind
    || parseTags(draft.tags).join("\u0000") !== parseTags(initial.tags).join("\u0000")
    || draft.metadata.trim() !== initial.metadata.trim();
}

export type KindFilter = MemoryKind | "all";

/** "All" plus each kind present in these records, with counts. */
export function kindFilters(records: readonly MemoryRecord[]): { value: KindFilter; label: string; count: number }[] {
  const present = MEMORY_KINDS.filter((kind) => records.some((record) => record.kind === kind.value));
  return [
    { value: "all", label: "All", count: records.length },
    ...present.map((kind) => ({ value: kind.value, label: kind.label, count: records.filter((record) => record.kind === kind.value).length })),
  ];
}

export function filterByKind(records: readonly MemoryRecord[], kind: KindFilter): MemoryRecord[] {
  return kind === "all" ? [...records] : records.filter((record) => record.kind === kind);
}

/** A one-line excerpt, for example to name a memory in a delete confirmation. */
export function summarize(content: string, max = 120): string {
  const flat = content.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

/**
 * Whether a record was changed after it was added. The server stamps `created_at` and
 * `updated_at` separately on creation (microseconds apart), so equality is not enough.
 */
export function wasEdited(record: Pick<MemoryRecord, "created_at" | "updated_at">): boolean {
  return Date.parse(record.updated_at) - Date.parse(record.created_at) > 1000;
}
