/**
 * Pure view logic for the Tools page: search, filters, Agent eligibility, the operator
 * test-run form and per-tool history. Free of React for `node --test`.
 *
 * Nothing here decides whether a tool may run; the server does. These helpers only
 * describe what the API reports.
 */
import type { Agent } from "@/types/agents";
import type { ToolDefinition, ToolTask } from "@/types/tools";

export type AvailabilityFilter = "all" | "enabled" | "disabled";
export type EffectsFilter = "all" | "none" | "external";

export interface ToolFilters {
  query: string;
  availability: AvailabilityFilter;
  effects: EffectsFilter;
}

export function toolLabel(name: string): string {
  const words = name.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function filterTools(tools: readonly ToolDefinition[], filters: ToolFilters): ToolDefinition[] {
  const needle = filters.query.trim().toLowerCase();
  return tools.filter((tool) => {
    if (filters.availability === "enabled" && !tool.enabled) return false;
    if (filters.availability === "disabled" && tool.enabled) return false;
    if (filters.effects === "none" && tool.side_effects) return false;
    if (filters.effects === "external" && !tool.side_effects) return false;
    if (!needle) return true;
    return [tool.name, toolLabel(tool.name), tool.description, ...tool.capabilities].join(" ").toLowerCase().includes(needle);
  });
}

/** Filters worth showing: only when the tools actually differ on that dimension. */
export function availableFilters(tools: readonly ToolDefinition[]): { availability: boolean; effects: boolean } {
  return {
    availability: tools.some((tool) => tool.enabled) && tools.some((tool) => !tool.enabled),
    effects: tools.some((tool) => tool.side_effects) && tools.some((tool) => !tool.side_effects),
  };
}

/** Agents whose allowed tools include this one: the server's per-Agent gate checks the same list. */
export function agentsAllowing(tool: ToolDefinition, agents: readonly Agent[]): Agent[] {
  return agents.filter((agent) => agent.allowed_tools.includes(tool.name));
}

/** Permissions the tool declares, ignoring the "none" placeholder. */
export function declaredPermissions(tool: ToolDefinition): string[] {
  return tool.permissions.filter((permission) => permission !== "none");
}

export function tasksForTool(tasks: readonly ToolTask[], toolName: string): ToolTask[] {
  return tasks.filter((task) => task.tool_name === toolName);
}

// ------------------------------------------------------------------ operator test run

export interface TestField {
  name: string;
  label: string;
  helper: string;
  type: "text" | "number";
  placeholder?: string;
  min?: number;
  max?: number;
  integer?: boolean;
}

/**
 * Inputs for the operator test run, mirroring the server's built-in tool parameters
 * (backend/app/core/tool_runtime/domain/tool.py). The API doesn't publish those schemas
 * yet, so this list is kept in step by hand; the server validates every argument anyway.
 */
export const TEST_FIELDS: Readonly<Record<string, readonly TestField[]>> = {
  echo: [{ name: "message", label: "Message", helper: "Returned exactly as written.", type: "text", placeholder: "Hello Genesis" }],
  calculator: [{ name: "expression", label: "Expression", helper: "Safe arithmetic only, for example 2 + 5 * 10.", type: "text", placeholder: "2 + 5 * 10" }],
  random_number: [
    { name: "min", label: "Minimum", helper: "Whole number, inclusive.", type: "number", placeholder: "1", integer: true },
    { name: "max", label: "Maximum", helper: "Whole number, inclusive.", type: "number", placeholder: "100", integer: true },
  ],
  delay: [{ name: "seconds", label: "Seconds", helper: "From 0 to 60.", type: "number", placeholder: "2", min: 0, max: 60 }],
  simulated_action: [{ name: "note", label: "Note", helper: "Any text. Nothing leaves Genesis.", type: "text", placeholder: "Try the approval flow" }],
  uuid: [],
};

/** `undefined` when the page doesn't know this tool's inputs (the server still does). */
export function testFieldsFor(toolName: string): readonly TestField[] | undefined {
  return TEST_FIELDS[toolName];
}

/** Turn form values into arguments, or explain what to fix before sending anything. */
export function buildArguments(fields: readonly TestField[], values: Readonly<Record<string, string>>): { arguments: Record<string, unknown>; errors: null } | { arguments: null; errors: Record<string, string> } {
  const args: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  for (const field of fields) {
    const raw = (values[field.name] ?? "").trim();
    if (!raw) { errors[field.name] = `${field.label} is required.`; continue; }
    if (field.type === "text") { args[field.name] = raw; continue; }
    const value = Number(raw);
    if (!Number.isFinite(value)) errors[field.name] = `${field.label} must be a number.`;
    else if (field.integer && !Number.isInteger(value)) errors[field.name] = `${field.label} must be a whole number.`;
    else if (field.min !== undefined && value < field.min) errors[field.name] = `${field.label} must be at least ${field.min}.`;
    else if (field.max !== undefined && value > field.max) errors[field.name] = `${field.label} must be at most ${field.max}.`;
    else args[field.name] = value;
  }
  return Object.keys(errors).length ? { arguments: null, errors } : { arguments: args, errors: null };
}
