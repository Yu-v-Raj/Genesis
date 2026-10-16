/**
 * The command palette's commands, search and shortcut rules. Pure (no React, no browser
 * globals) so it can be tested with `node --test`.
 *
 * Navigation commands come from lib/navigation.ts, the single source of truth for
 * destinations. Actions are limited to flows the app already supports; none of them runs
 * anything on the server by itself — each opens the page where the user confirms.
 */
import type { NavItem } from "./navigation.ts";

export type CommandGroup = "Go to" | "Actions";

export interface Command {
  id: string;
  label: string;
  group: CommandGroup;
  /** Extra words that should find this command. */
  keywords: readonly string[];
  hint?: string;
  /** Navigate here when chosen… */
  href?: string;
  /** …or run a purely client-side action (no server request). */
  action?: "toggle-sidebar";
}

/** Words people may type for each destination, beyond its label. */
const NAV_KEYWORDS: Readonly<Record<string, readonly string[]>> = {
  "/": ["home", "dashboard", "overview", "summary"],
  "/agents": ["agent", "chat", "conversation", "assistant"],
  "/memory": ["memories", "remember", "facts", "knowledge"],
  "/workflows": ["workflow", "pipeline", "steps", "runs", "automation"],
  "/monitoring": ["operations", "monitoring", "executions", "runs", "events", "logs", "services"],
  "/tools": ["tool", "capabilities", "calculator"],
  "/providers": ["provider", "models", "llm", "gemini", "openai", "api key"],
  "/approvals": ["approval", "approve", "reject", "pending", "decision", "consent", "permission"],
};

export function buildCommands(navItems: readonly NavItem[], sidebarCollapsed: boolean): Command[] {
  const navigation: Command[] = navItems.map((item) => ({
    id: `go:${item.href}`,
    label: item.label,
    group: "Go to",
    keywords: NAV_KEYWORDS[item.href] ?? [],
    hint: item.description,
    href: item.href,
  }));
  const actions: Command[] = [
    { id: "action:create-agent", label: "Create Agent", group: "Actions", keywords: ["new agent", "add agent"], hint: "Opens the Agent creation form", href: "/agents?create=1" },
    { id: "action:create-workflow", label: "Create workflow", group: "Actions", keywords: ["new workflow", "add workflow", "builder"], hint: "Opens the workflow builder (saving doesn't run anything)", href: "/workflows?create=1" },
    { id: "action:toggle-sidebar", label: sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar", group: "Actions", keywords: ["sidebar", "navigation", "collapse", "expand"], action: "toggle-sidebar" },
  ];
  return [...navigation, ...actions];
}

/**
 * Case-insensitive match: every word of the query must appear in the label or keywords.
 * Labels that start with the query rank first; otherwise the original order is kept.
 */
export function filterCommands(commands: readonly Command[], query: string): Command[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...commands];
  const needle = words.join(" ");
  return commands
    .map((command, index) => ({ command, index, haystack: [command.label, ...command.keywords].join(" ").toLowerCase() }))
    .filter(({ haystack }) => words.every((word) => haystack.includes(word)))
    .sort((a, b) => Number(b.command.label.toLowerCase().startsWith(needle)) - Number(a.command.label.toLowerCase().startsWith(needle)) || a.index - b.index)
    .map(({ command }) => command);
}

/** Keep the highlighted row valid as results change: same command if still present, else the first. */
export function nextActiveId(results: readonly Command[], currentId: string | null): string | null {
  if (results.length === 0) return null;
  return currentId && results.some((command) => command.id === currentId) ? currentId : results[0].id;
}

/** Move the highlight with wrap-around (ArrowDown = +1, ArrowUp = -1). */
export function moveActive(results: readonly Command[], currentId: string | null, step: 1 | -1): string | null {
  if (results.length === 0) return null;
  const index = results.findIndex((command) => command.id === currentId);
  if (index === -1) return results[step === 1 ? 0 : results.length - 1].id;
  return results[(index + step + results.length) % results.length].id;
}

export interface ShortcutEvent {
  key: string;
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
  isComposing?: boolean;
  repeat?: boolean;
}

/**
 * ⌘K on macOS, Ctrl+K elsewhere. On macOS Ctrl+K is left alone: in text fields it deletes to
 * the end of the line. A plain "k" (normal typing) never matches.
 */
export function isPaletteShortcut(event: ShortcutEvent, isMac: boolean): boolean {
  if (event.isComposing || event.repeat || event.altKey || event.shiftKey) return false;
  if (event.key.toLowerCase() !== "k") return false;
  return isMac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
}

export function isMacPlatform(platform: string): boolean {
  return /mac|iphone|ipad|ipod/i.test(platform);
}
