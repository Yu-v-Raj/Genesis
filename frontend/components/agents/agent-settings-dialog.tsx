"use client";

import { FormEvent, useId, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, LoaderCircle, Plus, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert } from "@/components/ui/feedback";
import { Field, Input, Textarea } from "@/components/ui/field";
import { isModelConfigured, modelKey, providerLabel } from "@/lib/agent-experience";
import { cn } from "@/lib/utils";
import type { Agent, AgentConfigurationInput, CreateAgentInput, LLMModelOption, LLMModelRef } from "@/types/agents";
import type { ToolDefinition } from "@/types/tools";

const DEFAULT_TOOLS = ["calculator"];
const MAX_INSTRUCTIONS = 4000;
const MAX_NAME = 120;

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

function sameTools(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((tool) => b.includes(tool));
}

/**
 * Create an Agent, or change an existing Agent's model, tools and instructions. The fields,
 * defaults and request are unchanged; closing with unsaved edits asks first.
 */
export function AgentSettingsDialog({ agent, models, tools, optionsError, onClose, onCreate, onUpdate }: AgentSettingsDialogProps) {
  const editing = agent !== null;
  const ids = useId();
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
  const [nameError, setNameError] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  // A ref, not state: two clicks in the same frame must not both reach the server.
  const inFlight = useRef(false);

  // Models load asynchronously; preselect a sensible one unless the user already chose.
  const effectiveModel = modelTouched ? model : (model ?? defaultModel(models));
  const selectedModel = models?.find((option) => effectiveModel !== null && modelKey(option) === modelKey(effectiveModel));

  const dirty = editing
    ? instructions !== agent.instructions || !sameTools(allowedTools, agent.allowed_tools) || (modelTouched && (model === null ? agent.llm_model !== null : agent.llm_model === null || modelKey(model) !== modelKey(agent.llm_model)))
    : Boolean(name.trim() || instructions.trim() || description.trim() || tags.trim() || type !== "assistant" || modelTouched || !sameTools(allowedTools, DEFAULT_TOOLS));

  /** Escape, the close button, the backdrop and Cancel all come here; only "Discard" drops edits. */
  function requestClose() {
    if (submitting) return;
    if (confirmDiscard) { setConfirmDiscard(false); return; }
    if (dirty) { setConfirmDiscard(true); return; }
    onClose();
  }

  function toggleTool(toolName: string) {
    setAllowedTools((current) => current.includes(toolName) ? current.filter((item) => item !== toolName) : [...current, toolName]);
  }

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (inFlight.current) return;
    if (!editing && !name.trim()) {
      setNameError("Give your Agent a name.");
      nameRef.current?.focus();
      return;
    }
    if (effectiveModel === null) {
      setError("Choose a model for this Agent.");
      return;
    }
    setNameError(null);
    setError(null);
    inFlight.current = true;
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
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  const formId = `${ids}-form`;
  const footer = confirmDiscard ? (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between" role="alert">
      <p className="text-sm text-foreground">Discard your unsaved changes?</p>
      <div className="flex gap-2 sm:justify-end">
        <Button size="sm" onClick={() => setConfirmDiscard(false)} autoFocus>Keep editing</Button>
        <Button size="sm" variant="danger" onClick={onClose}>Discard</Button>
      </div>
    </div>
  ) : (
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <Button onClick={requestClose} disabled={submitting}>Cancel</Button>
      <Button type="submit" form={formId} variant="primary" loading={submitting} disabled={models === null}
        icon={editing ? <Save aria-hidden className="h-4 w-4" /> : <Plus aria-hidden className="h-4 w-4" />}>
        {submitting ? "Saving…" : editing ? "Save changes" : "Create Agent"}
      </Button>
    </div>
  );

  return (
    <Dialog
      open
      onClose={requestClose}
      size="lg"
      title={editing ? `${agent.name} settings` : "Create an Agent"}
      description={editing ? "Change the model, the tools it may use and its instructions." : "Give it a name and a purpose, then choose its model and tools. It's ready to chat as soon as it's created."}
      footer={footer}
    >
      <form id={formId} onSubmit={submit} noValidate className="flex flex-col gap-6">
        <section aria-labelledby={`${ids}-basics`} className="flex flex-col gap-4">
          <h3 id={`${ids}-basics`} className="text-xs font-medium uppercase tracking-wider text-subtle">Basics</h3>
          {!editing && (
            <Field label={<>Name <span className="text-danger" aria-hidden>*</span><span className="sr-only">(required)</span></>} error={nameError} hint={`Up to ${MAX_NAME} characters.`}>
              {(props) => <Input {...props} ref={nameRef} value={name} onChange={(event) => { setName(event.target.value); if (nameError) setNameError(null); }} placeholder="e.g. Research assistant" maxLength={MAX_NAME} autoComplete="off" required data-autofocus />}
            </Field>
          )}
          <Field label="What should this Agent do?" hint={<>Optional. Sent to the model as standing instructions with every message. <span className="tabular-nums">{instructions.length}/{MAX_INSTRUCTIONS}</span></>}>
            {(props) => <Textarea {...props} value={instructions} onChange={(event) => setInstructions(event.target.value)} rows={4} maxLength={MAX_INSTRUCTIONS} placeholder="e.g. Answer questions about our product. Be concise and use the calculator for arithmetic." data-autofocus={editing ? true : undefined} />}
          </Field>
        </section>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-xs font-medium uppercase tracking-wider text-subtle">Model <span className="text-danger" aria-hidden>*</span><span className="sr-only">(required)</span></legend>
          {models === null ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              {optionsError ? <><AlertTriangle aria-hidden className="h-4 w-4 text-warning" />{optionsError}</> : <><LoaderCircle aria-hidden className="h-4 w-4 animate-spin" />Loading models…</>}
            </p>
          ) : models.length === 0 ? (
            <p className="text-sm text-muted-foreground">This Genesis server has no model providers registered.</p>
          ) : (
            <div className="grid gap-2">
              {models.map((option) => {
                const configured = isModelConfigured(option);
                const checked = effectiveModel !== null && modelKey(option) === modelKey(effectiveModel);
                return (
                  <label key={modelKey(option)} className={cn("flex cursor-pointer items-center justify-between gap-3 rounded-md border px-3 py-2.5 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent", checked ? "border-accent/60 bg-accent/[0.06]" : "border-border hover:bg-white/[0.03]")}>
                    <span className="flex min-w-0 items-center gap-3">
                      <input type="radio" name={`${ids}-model`} checked={checked} onChange={() => { setModel({ provider: option.provider, model_name: option.model_name }); setModelTouched(true); }} className="accent-[var(--color-accent)]" />
                      <span className="min-w-0">
                        <span className="font-medium text-foreground">{providerLabel(option.provider)}</span>
                        <span className="ml-2 break-all font-mono text-xs text-muted-foreground">{option.model_name}</span>
                      </span>
                    </span>
                    {/* "Key configured" is what the server knows; it doesn't prove requests succeed. */}
                    {configured
                      ? <span className="inline-flex shrink-0 items-center gap-1 text-xs text-success"><CheckCircle2 aria-hidden className="h-3.5 w-3.5" />Key configured</span>
                      : <span className="inline-flex shrink-0 items-center gap-1 text-xs text-warning"><AlertTriangle aria-hidden className="h-3.5 w-3.5" />No API key</span>}
                  </label>
                );
              })}
            </div>
          )}
          {models !== null && models.length > 0 && !models.some(isModelConfigured) && effectiveModel === null && (
            <p role="note" className="text-xs leading-5 text-muted-foreground">No provider has an API key on this server yet. You can still create the Agent; it will answer once a key is added.</p>
          )}
          {selectedModel && !isModelConfigured(selectedModel) && (
            <Alert tone="warning">
              <span className="text-xs leading-5">The server has no API key for {providerLabel(selectedModel.provider)}, so this Agent can&apos;t answer yet. An administrator adds it to the backend <code className="font-mono">.env</code> file and restarts the backend — never paste keys into a chat.</span>
            </Alert>
          )}
        </fieldset>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-xs font-medium uppercase tracking-wider text-subtle">Tools it may use</legend>
          <p className="mb-1 text-xs text-muted-foreground">The Agent can only call the tools you allow; the server checks every request.</p>
          {tools === null ? (
            <p className="text-sm text-muted-foreground" role="status">{optionsError ?? "Loading tools…"}</p>
          ) : tools.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tools are registered.</p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {tools.map((tool) => {
                const checked = allowedTools.includes(tool.name);
                return (
                  <label key={tool.name} className={cn("flex cursor-pointer items-start gap-2.5 rounded-md border px-3 py-2 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent", checked ? "border-accent/40 bg-accent/[0.04]" : "border-border hover:bg-white/[0.03]", !tool.enabled && "cursor-not-allowed opacity-50")}>
                    <input type="checkbox" checked={checked} onChange={() => toggleTool(tool.name)} disabled={!tool.enabled} className="mt-0.5 accent-[var(--color-accent)]" />
                    <span className="min-w-0">
                      <span className="font-medium text-foreground">{tool.name.replaceAll("_", " ")}</span>
                      <span className="block text-xs leading-5 text-muted-foreground">{tool.description}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          )}
        </fieldset>

        {!editing && (
          <details className="group rounded-md border border-border">
            <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
              <ChevronRight aria-hidden className="h-4 w-4 transition-transform group-open:rotate-90" />
              Advanced — description, type and tags
            </summary>
            <div className="flex flex-col gap-4 border-t border-border p-3">
              <Field label="Short description" hint="Shown in the Agents list. If empty, the first line of the instructions is used.">
                {(props) => <Input {...props} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="e.g. Answers product questions" />}
              </Field>
              <Field label="Type" hint="A free-form category, for example “assistant” or “researcher”.">
                {(props) => <Input {...props} value={type} onChange={(event) => setType(event.target.value)} />}
              </Field>
              <Field label="Tags" hint="Comma separated.">
                {(props) => <Input {...props} value={tags} onChange={(event) => setTags(event.target.value)} placeholder="e.g. support, internal" />}
              </Field>
            </div>
          </details>
        )}

        {error && <Alert tone="danger">{error}</Alert>}
        {/* Enter in a single-line field submits; the hidden button keeps that native behaviour. */}
        <button type="submit" hidden aria-hidden tabIndex={-1} />
      </form>
    </Dialog>
  );
}

function summarize(text: string): string {
  const firstLine = text.trim().split("\n")[0] ?? "";
  return firstLine.length > 140 ? `${firstLine.slice(0, 137)}…` : firstLine;
}
