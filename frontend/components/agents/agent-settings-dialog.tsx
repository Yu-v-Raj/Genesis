"use client";

import { FormEvent, KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, LoaderCircle, Plus, Save, X } from "lucide-react";

import { isModelConfigured, modelKey, providerLabel } from "@/lib/agent-experience";
import type { Agent, AgentConfigurationInput, CreateAgentInput, LLMModelOption, LLMModelRef } from "@/types/agents";
import type { ToolDefinition } from "@/types/tools";

const DEFAULT_TOOLS = ["calculator"];
const MAX_INSTRUCTIONS = 4000;

interface AgentSettingsDialogProps {
  /** `null` creates a new Agent; an Agent edits that Agent's configuration. */
  agent: Agent | null;
  models: LLMModelOption[] | null;
  tools: ToolDefinition[] | null;
  optionsError: string | null;
  onClose: () => void;
  onCreate: (input: CreateAgentInput) => Promise<Agent | null>;
  onUpdate: (agentId: string, input: AgentConfigurationInput) => Promise<Agent | null>;
}

/** Preselect only a model the server can actually use; otherwise make the user choose. */
function defaultModel(models: LLMModelOption[] | null): LLMModelRef | null {
  const choice = models?.find(isModelConfigured);
  return choice ? { provider: choice.provider, model_name: choice.model_name } : null;
}

/** Create an Agent, or change an existing Agent's model, tools, and instructions. */
export function AgentSettingsDialog({ agent, models, tools, optionsError, onClose, onCreate, onUpdate }: AgentSettingsDialogProps) {
  const editing = agent !== null;
  const ids = useId();
  const dialogRef = useRef<HTMLFormElement>(null);
  const firstFieldRef = useRef<HTMLInputElement & HTMLTextAreaElement>(null);
  const [name, setName] = useState("");
  const [instructions, setInstructions] = useState(agent?.instructions ?? "");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("assistant");
  const [tags, setTags] = useState("");
  const [model, setModel] = useState<LLMModelRef | null>(agent ? agent.llm_model : defaultModel(models));
  const [modelTouched, setModelTouched] = useState(editing);
  const [allowedTools, setAllowedTools] = useState<string[]>(agent?.allowed_tools ?? DEFAULT_TOOLS);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Models load asynchronously; preselect a sensible one unless the user already chose.
  const effectiveModel = modelTouched ? model : (model ?? defaultModel(models));

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    firstFieldRef.current?.focus();
    return () => previouslyFocused?.focus();
  }, []);

  function trapFocus(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Escape" && !submitting) {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab" || dialogRef.current === null) return;
    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>("button, input, textarea, select, summary, [tabindex]:not([tabindex='-1'])")
    ).filter((element) => !element.hasAttribute("disabled"));
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }

  function toggleTool(toolName: string) {
    setAllowedTools((current) => current.includes(toolName) ? current.filter((item) => item !== toolName) : [...current, toolName]);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    if (!editing && !name.trim()) {
      setError("Give your Agent a name.");
      return;
    }
    if (effectiveModel === null) {
      setError("Choose a model for this Agent.");
      return;
    }
    setError(null);
    setSubmitting(true);
    const configuration: AgentConfigurationInput = {
      llm_model: effectiveModel,
      allowed_tools: allowedTools,
      instructions: instructions.trim(),
    };
    try {
      const saved = editing
        ? await onUpdate(agent.id, configuration)
        : await onCreate({
            ...configuration,
            name: name.trim(),
            description: description.trim() || summarize(instructions) || "General-purpose assistant.",
            type: type.trim() || "assistant",
            tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
            initialize: true,
          });
      if (saved) onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The Agent could not be saved.");
    } finally {
      setSubmitting(false);
    }
  }

  const fieldClass = "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 hover:border-white/15 focus:border-primary focus-visible:ring-2 focus-visible:ring-primary/40";
  const selectedModel = models?.find((option) => effectiveModel !== null && modelKey(option) === modelKey(effectiveModel));

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 backdrop-blur-sm sm:items-center sm:p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !submitting) onClose(); }}>
      <form
        ref={dialogRef}
        onSubmit={submit}
        onKeyDown={trapFocus}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${ids}-title`}
        aria-describedby={`${ids}-subtitle`}
        className="flex max-h-[92vh] w-full max-w-xl flex-col rounded-t-2xl border border-border bg-surface shadow-2xl shadow-black/40 sm:rounded-xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-border p-5">
          <div>
            <h2 id={`${ids}-title`} className="text-lg font-semibold tracking-tight text-foreground">
              {editing ? `${agent.name} settings` : "Create an Agent"}
            </h2>
            <p id={`${ids}-subtitle`} className="mt-1 text-sm text-muted-foreground">
              {editing ? "Change the model, permitted tools, and instructions." : "Pick a model and the tools it may use. It will be ready to chat right away."}
            </p>
          </div>
          <button type="button" onClick={onClose} disabled={submitting} className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground disabled:opacity-50" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="grid gap-6 overflow-y-auto p-5">
          {!editing && (
            <label className="grid gap-1.5 text-sm font-medium text-foreground">
              Name
              <input ref={firstFieldRef} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Math helper" className={fieldClass} required maxLength={120} />
            </label>
          )}

          <label className="grid gap-1.5 text-sm font-medium text-foreground">
            What should this Agent do?
            <textarea
              ref={editing ? firstFieldRef : undefined}
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              rows={3}
              maxLength={MAX_INSTRUCTIONS}
              placeholder="e.g. Answer arithmetic questions. Always use the calculator and reply in one short sentence."
              className={fieldClass}
            />
            <span className="text-xs font-normal text-muted-foreground">Optional. Sent to the model as standing instructions for every message.</span>
          </label>

          <fieldset className="grid gap-2">
            <legend className="mb-2 text-sm font-medium text-foreground">Model</legend>
            {models === null ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                {optionsError ? <><AlertTriangle className="h-4 w-4 text-amber-300" />{optionsError}</> : <><LoaderCircle className="h-4 w-4 animate-spin" />Loading models…</>}
              </p>
            ) : models.length === 0 ? (
              <p className="text-sm text-muted-foreground">This Genesis server has no LLM providers registered.</p>
            ) : (
              models.map((option) => {
                const configured = isModelConfigured(option);
                const checked = effectiveModel !== null && modelKey(option) === modelKey(effectiveModel);
                return (
                  <label key={modelKey(option)} className={`flex cursor-pointer items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors ${checked ? "border-primary/60 bg-primary/[0.07]" : "border-border hover:bg-white/[0.03]"}`}>
                    <span className="flex items-center gap-3">
                      <input type="radio" name={`${ids}-model`} checked={checked} onChange={() => { setModel({ provider: option.provider, model_name: option.model_name }); setModelTouched(true); }} className="accent-primary" />
                      <span>
                        <span className="font-medium text-foreground">{providerLabel(option.provider)}</span>
                        <span className="ml-2 font-mono text-xs text-muted-foreground">{option.model_name}</span>
                      </span>
                    </span>
                    {configured ? (
                      <span className="inline-flex items-center gap-1 text-xs text-emerald-300"><CheckCircle2 className="h-3.5 w-3.5" />Ready</span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-amber-300"><AlertTriangle className="h-3.5 w-3.5" />No API key</span>
                    )}
                  </label>
                );
              })
            )}
            {models !== null && models.length > 0 && !models.some(isModelConfigured) && effectiveModel === null && (
              <p role="note" className="text-xs leading-5 text-muted-foreground">
                No provider has an API key on this server yet. You can still create the Agent; it will answer once a key is added.
              </p>
            )}
            {selectedModel && !isModelConfigured(selectedModel) && (
              <p role="note" className="rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs leading-5 text-amber-100">
                The server has no API key for {providerLabel(selectedModel.provider)}, so this Agent can&apos;t answer yet. Add the key to the backend <code>.env</code> file and restart the backend.
              </p>
            )}
          </fieldset>

          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium text-foreground">Tools it may use</legend>
            <p className="mb-1 text-xs text-muted-foreground">The Agent can only call the tools you allow; every request is still checked by the server.</p>
            {tools === null ? (
              <p className="text-sm text-muted-foreground">{optionsError ?? "Loading tools…"}</p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {tools.map((tool) => (
                  <label key={tool.name} className={`flex cursor-pointer items-start gap-2.5 rounded-lg border border-border px-3 py-2 text-sm hover:bg-white/[0.03] ${tool.enabled ? "" : "opacity-50"}`}>
                    <input type="checkbox" checked={allowedTools.includes(tool.name)} onChange={() => toggleTool(tool.name)} disabled={!tool.enabled} className="mt-0.5 accent-primary" />
                    <span>
                      <span className="font-medium text-foreground">{tool.name.replaceAll("_", " ")}</span>
                      <span className="block text-xs text-muted-foreground">{tool.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            )}
          </fieldset>

          {!editing && (
            <details className="rounded-lg border border-border px-3 py-2 text-sm">
              <summary className="cursor-pointer text-muted-foreground">More options</summary>
              <div className="mt-3 grid gap-4 pb-1">
                <label className="grid gap-1.5 font-medium text-foreground">Short description<input value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Shown on the Agent's card" className={fieldClass} /></label>
                <label className="grid gap-1.5 font-medium text-foreground">Type<input value={type} onChange={(event) => setType(event.target.value)} className={fieldClass} /></label>
                <label className="grid gap-1.5 font-medium text-foreground">Tags<input value={tags} onChange={(event) => setTags(event.target.value)} placeholder="Comma separated" className={fieldClass} /></label>
              </div>
            </details>
          )}

          {error && <p role="alert" className="rounded-lg border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm text-red-200">{error}</p>}
        </div>

        <footer className="flex flex-col-reverse gap-2 border-t border-border p-4 sm:flex-row sm:justify-end">
          <button type="button" onClick={onClose} disabled={submitting} className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:bg-white/5 disabled:opacity-50">Cancel</button>
          <button type="submit" disabled={submitting || models === null} className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-50">
            {submitting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : editing ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {submitting ? "Saving…" : editing ? "Save changes" : "Create Agent"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function summarize(text: string): string {
  const firstLine = text.trim().split("\n")[0] ?? "";
  return firstLine.length > 140 ? `${firstLine.slice(0, 137)}…` : firstLine;
}
