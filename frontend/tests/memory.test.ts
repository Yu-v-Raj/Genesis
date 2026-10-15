import assert from "node:assert/strict";
import test from "node:test";

import type { MemoryRecord } from "../types/memory.ts";
import {
  MAX_CONTENT, draftFrom, filterByKind, isDraftDirty, kindFilters, kindLabel, parseMetadata, parseTags, summarize, validateDraft,
} from "../lib/memory.ts";

function record(overrides: Partial<MemoryRecord> = {}): MemoryRecord {
  return {
    memory_id: "m1", agent_id: "a1", content: "My project codename is ORION-742.", kind: "note",
    created_at: "2026-10-13T16:53:35Z", updated_at: "2026-10-13T16:53:35Z", metadata: { source: "operator" }, tags: ["project", "testing"], ...overrides,
  };
}

test("tags are trimmed, de-duplicated and blank-free", () => {
  assert.deepEqual(parseTags(" project, testing ,, project "), ["project", "testing"]);
  assert.deepEqual(parseTags(""), []);
});

test("metadata must be a JSON object; blank means none", () => {
  assert.deepEqual(parseMetadata(""), {});
  assert.deepEqual(parseMetadata('{"source":"operator"}'), { source: "operator" });
  assert.equal(parseMetadata("[1,2]"), null);
  assert.equal(parseMetadata("not json"), null);
  assert.equal(parseMetadata("42"), null);
});

test("validation mirrors the server's rules and builds the unchanged payload", () => {
  const ok = validateDraft({ content: "  Prefers metric units  ", kind: "preference", tags: "units, units", metadata: "" });
  assert.deepEqual(ok, { input: { content: "Prefers metric units", kind: "preference", tags: ["units"], metadata: {} }, errors: null });

  const empty = validateDraft({ content: "   ", kind: "note", tags: "", metadata: "{" });
  assert.equal(empty.input, null);
  assert.ok(empty.errors?.content && empty.errors.metadata);

  const long = validateDraft({ content: "x".repeat(MAX_CONTENT + 1), kind: "note", tags: "", metadata: "" });
  assert.match(long.errors?.content ?? "", /10,000/);
  assert.equal(validateDraft({ content: "x".repeat(MAX_CONTENT), kind: "note", tags: "", metadata: "" }).errors, null);
});

test("an edit starts from the stored values and is clean until changed", () => {
  const initial = draftFrom(record());
  assert.deepEqual(initial, { content: "My project codename is ORION-742.", kind: "note", tags: "project, testing", metadata: '{\n  "source": "operator"\n}' });
  assert.equal(isDraftDirty(initial, initial), false);
  assert.equal(isDraftDirty({ ...initial, tags: "project,testing" }, initial), false); // spacing only
  assert.equal(isDraftDirty({ ...initial, kind: "fact" }, initial), true);
  assert.deepEqual(draftFrom(null), { content: "", kind: "note", tags: "", metadata: "" });
});

test("kind filters list only kinds present, with counts", () => {
  const records = [record({ memory_id: "1" }), record({ memory_id: "2", kind: "fact" }), record({ memory_id: "3" })];
  assert.deepEqual(kindFilters(records).map((f) => [f.value, f.count]), [["all", 3], ["fact", 1], ["note", 2]]);
  assert.deepEqual(filterByKind(records, "fact").map((r) => r.memory_id), ["2"]);
  assert.equal(filterByKind(records, "all").length, 3);
  assert.equal(kindLabel("preference"), "Preference");
});

test("summaries flatten whitespace and stay short", () => {
  assert.equal(summarize("a\n\n  b"), "a b");
  assert.equal(summarize("x".repeat(200), 10), "xxxxxxxxx…");
});

test("a record counts as edited only when it changed after being added", async () => {
  const { wasEdited } = await import("../lib/memory.ts");
  assert.equal(wasEdited({ created_at: "2026-10-13T16:53:35.801496Z", updated_at: "2026-10-13T16:53:35.801503Z" }), false);
  assert.equal(wasEdited({ created_at: "2026-10-13T16:53:35Z", updated_at: "2026-10-13T17:10:00Z" }), true);
});
