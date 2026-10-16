import assert from "node:assert/strict";
import test from "node:test";

import { NAV_ITEMS } from "../lib/navigation.ts";
import { buildCommands, filterCommands, isMacPlatform, isPaletteShortcut, moveActive, nextActiveId, type ShortcutEvent } from "../lib/commands.ts";

const commands = buildCommands(NAV_ITEMS, false);
const labels = (query: string) => filterCommands(commands, query).map((command) => command.label);
const key = (overrides: Partial<ShortcutEvent>): ShortcutEvent => ({ key: "k", metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...overrides });

test("navigation commands come from the shared navigation, one per destination", () => {
  const go = commands.filter((command) => command.group === "Go to");
  assert.deepEqual(go.map((command) => command.href), NAV_ITEMS.map((item) => item.href));
  assert.deepEqual(go.map((command) => command.label), ["Overview", "Agents", "Memory", "Workflows", "Operations", "Approvals", "Tools", "Providers"]);
});

test("actions only open existing flows or change a local preference", () => {
  const actions = commands.filter((command) => command.group === "Actions");
  assert.deepEqual(actions.map((command) => command.href ?? command.action), ["/agents?create=1", "/workflows?create=1", "toggle-sidebar"]);
  assert.equal(buildCommands(NAV_ITEMS, true).at(-1)?.label, "Expand sidebar");
  assert.equal(buildCommands(NAV_ITEMS, false).at(-1)?.label, "Collapse sidebar");
});

test("search ignores case, matches keywords, and needs every word", () => {
  assert.deepEqual(labels("MEMORY"), ["Memory"]);
  assert.deepEqual(labels("gemini"), ["Providers"]);
  assert.deepEqual(labels("logs"), ["Operations"]);
  assert.deepEqual(labels("new agent"), ["Create Agent"]);
  assert.deepEqual(labels("create"), ["Create Agent", "Create workflow"]);
  assert.deepEqual(labels("zzz"), []);
  assert.equal(labels("   ").length, commands.length); // cleared query shows everything
});

test("labels that start with the query rank first", () => {
  assert.equal(labels("work")[0], "Workflows");
  assert.equal(labels("agent")[0], "Agents");
});

test("the highlighted row stays valid while filtering", () => {
  const all = filterCommands(commands, "");
  assert.equal(nextActiveId(all, null), all[0].id);
  assert.equal(nextActiveId(filterCommands(commands, "mem"), "go:/memory"), "go:/memory");
  assert.equal(nextActiveId(filterCommands(commands, "tool"), "go:/memory"), "go:/tools");
  assert.equal(nextActiveId([], "go:/memory"), null);
});

test("arrow keys move and wrap around", () => {
  const results = filterCommands(commands, "create");
  assert.equal(moveActive(results, results[0].id, 1), results[1].id);
  assert.equal(moveActive(results, results[1].id, 1), results[0].id);
  assert.equal(moveActive(results, results[0].id, -1), results[1].id);
  assert.equal(moveActive([], null, 1), null);
});

test("the shortcut is ⌘K on macOS and Ctrl+K elsewhere; plain typing never opens it", () => {
  assert.equal(isPaletteShortcut(key({ metaKey: true }), true), true);
  assert.equal(isPaletteShortcut(key({ key: "K", metaKey: true }), true), true);
  assert.equal(isPaletteShortcut(key({ ctrlKey: true }), false), true);
  assert.equal(isPaletteShortcut(key({}), true), false); // typing "k"
  assert.equal(isPaletteShortcut(key({}), false), false);
  assert.equal(isPaletteShortcut(key({ ctrlKey: true }), true), false); // macOS Ctrl+K = delete to end of line
  assert.equal(isPaletteShortcut(key({ metaKey: true }), false), false);
  assert.equal(isPaletteShortcut(key({ metaKey: true, shiftKey: true }), true), false);
  assert.equal(isPaletteShortcut(key({ metaKey: true, isComposing: true }), true), false);
  assert.equal(isPaletteShortcut(key({ metaKey: true, repeat: true }), true), false);
  assert.equal(isPaletteShortcut(key({ key: "j", metaKey: true }), true), false);
});

test("platform detection", () => {
  assert.equal(isMacPlatform("MacIntel"), true);
  assert.equal(isMacPlatform("iPhone"), true);
  assert.equal(isMacPlatform("Win32"), false);
  assert.equal(isMacPlatform("Linux x86_64"), false);
});
