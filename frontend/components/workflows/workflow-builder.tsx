"use client";

import { FormEvent, useId, useRef, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button, IconButton } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert } from "@/components/ui/feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { testFieldsFor, toolLabel } from "@/lib/tools";
import { hasErrors, parseArguments, validateBuilder, type DraftErrors, type DraftStep } from "@/lib/workflows";
import type { ToolDefinition } from "@/types/tools";
import type { WorkflowCreateRequest } from "@/types/workflows";

/** Example arguments for a tool, from the known test fields (the server validates them). */
function exampleArguments(toolName: string): string {
  const fields = testFieldsFor(toolName);
  if (!fields || fields.length === 0) return "{}";
  return JSON.stringify(Object.fromEntries(fields.map((field) => [field.name, field.type === "number" ? Number(field.placeholder ?? 0) : field.placeholder ?? ""])), null, 2);
}

let nextKey = 1;
const newStep = (index: number, toolName: string): DraftStep => ({ key: `step-${nextKey++}`, task_id: `step-${index + 1}`, name: "", tool_name: toolName, argumentsText: toolName ? exampleArguments(toolName) : "{}", dependencies: [] });

/**
 * Save a workflow (its steps call tools on the server, in dependency order). As before,
 * saving also creates a first run that is NOT started; starting is a separate, explicit step.
 */
export function WorkflowBuilder({ tools, onClose, onCreate }: { tools: readonly ToolDefinition[]; onClose: () => void; onCreate: (input: WorkflowCreateRequest) => Promise<string | null> }) {
  const ids = useId();
  const defaultTool = tools.find((tool) => tool.enabled)?.name ?? "";
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<DraftStep[]>(() => [newStep(0, defaultTool)]);
  const [errors, setErrors] = useState<DraftErrors>({ steps: {} });
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const inFlight = useRef(false);
  const dirty = name.trim() !== "" || description.trim() !== "" || steps.length > 1 || steps.some((step) => step.name.trim() !== "");

  function update(key: string, changes: Partial<DraftStep>) {
    setSteps((current) => current.map((step) => (step.key === key ? { ...step, ...changes } : step)));
  }

  function changeId(key: string, value: string) {
    // Keep dependencies pointing at the renamed step.
    setSteps((current) => {
      const previous = current.find((step) => step.key === key)?.task_id;
      return current.map((step) => step.key === key ? { ...step, task_id: value } : { ...step, dependencies: step.dependencies.map((dep) => (dep === previous ? value : dep)) });
    });
  }

  function removeStep(key: string) {
    setSteps((current) => {
      const removed = current.find((step) => step.key === key)?.task_id;
      return current.filter((step) => step.key !== key).map((step) => ({ ...step, dependencies: step.dependencies.filter((dep) => dep !== removed) }));
    });
  }

  function requestClose() {
    if (submitting) return;
    if (confirmDiscard) { setConfirmDiscard(false); return; }
    if (dirty) { setConfirmDiscard(true); return; }
    onClose();
  }

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (inFlight.current) return;
    const found = validateBuilder(name, steps, tools.map((tool) => tool.name));
    setErrors(found);
    if (hasErrors(found)) return;
    inFlight.current = true;
    setSubmitting(true);
    setServerError(null);
    try {
      const failure = await onCreate({
        name: name.trim(),
        description: description.trim(),
        metadata: {},
        tasks: steps.map((step) => ({ task_id: step.task_id.trim(), name: step.name.trim(), action: "tool" as const, tool_name: step.tool_name, tool_arguments: parseArguments(step.argumentsText) ?? {}, dependencies: step.dependencies })),
      });
      if (failure) setServerError(failure);
      else onClose();
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  const formId = `${ids}-form`;
  const footer = confirmDiscard ? (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between" role="alert">
      <p className="text-sm text-foreground">Discard this workflow?</p>
      <div className="flex gap-2 sm:justify-end">
        <Button size="sm" onClick={() => setConfirmDiscard(false)} autoFocus>Keep editing</Button>
        <Button size="sm" variant="danger" onClick={onClose}>Discard</Button>
      </div>
    </div>
  ) : (
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end">
      <p className="text-[11px] text-muted-foreground sm:mr-auto">Saving doesn&apos;t run anything.</p>
      <Button onClick={requestClose} disabled={submitting}>Cancel</Button>
      <Button type="submit" form={formId} variant="primary" loading={submitting}>{submitting ? "Saving…" : "Save workflow"}</Button>
    </div>
  );

  return (
    <Dialog open onClose={requestClose} size="lg" footer={footer} title="Create a workflow"
      description="A workflow is a list of tool steps the server runs for you. A step can wait for earlier steps; steps with nothing to wait for start together.">
      <form id={formId} onSubmit={submit} noValidate className="flex flex-col gap-5">
        <Field label={<>Name <span className="text-danger" aria-hidden>*</span><span className="sr-only">(required)</span></>} error={errors.name}>
          {(props) => <Input {...props} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Nightly totals" maxLength={200} data-autofocus autoComplete="off" />}
        </Field>
        <Field label="What it does" hint="Optional. Shown in the workflow list.">
          {(props) => <Textarea {...props} value={description} onChange={(event) => setDescription(event.target.value)} rows={2} className="min-h-16" />}
        </Field>

        <fieldset className="flex flex-col gap-3">
          <legend className="mb-1 text-xs font-medium uppercase tracking-wider text-subtle">Steps</legend>
          {steps.map((step, index) => {
            const stepErrors = errors.steps[step.key] ?? {};
            const earlier = steps.slice(0, index).filter((other) => other.task_id.trim());
            return (
              <div key={step.key} className="flex flex-col gap-3 rounded-md border border-border bg-surface-2/40 p-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium text-foreground">Step {index + 1}</p>
                  {steps.length > 1 && <IconButton label={`Remove step ${index + 1}`} onClick={() => removeStep(step.key)}><Trash2 aria-hidden className="h-3.5 w-3.5" /></IconButton>}
                </div>
                <div className="grid gap-3 sm:grid-cols-[1fr_1fr_1fr]">
                  <Field label="Name" error={stepErrors.name}>{(props) => <Input {...props} value={step.name} onChange={(event) => update(step.key, { name: event.target.value })} placeholder="e.g. Add totals" />}</Field>
                  <Field label="Step ID" error={stepErrors.task_id} hint="Unique; other steps refer to it.">{(props) => <Input {...props} value={step.task_id} onChange={(event) => changeId(step.key, event.target.value)} className="font-mono text-xs" />}</Field>
                  <Field label="Tool" error={stepErrors.tool_name}>
                    {(props) => (
                      <Select {...props} value={step.tool_name} onChange={(event) => update(step.key, { tool_name: event.target.value, argumentsText: exampleArguments(event.target.value) })}>
                        <option value="">Choose a tool</option>
                        {tools.map((tool) => <option key={tool.name} value={tool.name} disabled={!tool.enabled}>{toolLabel(tool.name)}{tool.enabled ? "" : " (disabled)"}{tool.side_effects ? " · may change things outside Genesis" : ""}</option>)}
                      </Select>
                    )}
                  </Field>
                </div>
                <Field label="Arguments (JSON object)" error={stepErrors.arguments} hint="Passed to the tool as written. The server checks them when the step runs.">
                  {(props) => <Textarea {...props} value={step.argumentsText} onChange={(event) => update(step.key, { argumentsText: event.target.value })} rows={3} spellCheck={false} className="min-h-20 font-mono text-xs" />}
                </Field>
                {earlier.length > 0 && (
                  <fieldset>
                    <legend className="mb-1.5 text-xs font-medium text-foreground">Wait for</legend>
                    <div className="flex flex-wrap gap-2">
                      {earlier.map((other) => {
                        const checked = step.dependencies.includes(other.task_id.trim());
                        return (
                          <label key={other.key} className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border px-2 py-1 text-xs text-foreground has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent">
                            <input type="checkbox" checked={checked} className="accent-[var(--color-accent)]"
                              onChange={() => update(step.key, { dependencies: checked ? step.dependencies.filter((dep) => dep !== other.task_id.trim()) : [...step.dependencies, other.task_id.trim()] })} />
                            {other.name.trim() || other.task_id}
                          </label>
                        );
                      })}
                    </div>
                    <p className="mt-1 text-[11px] text-subtle">{step.dependencies.length ? "Starts after the checked steps complete." : "Nothing checked: starts as soon as the run starts."}</p>
                  </fieldset>
                )}
              </div>
            );
          })}
          <Button size="sm" onClick={() => setSteps((current) => [...current, newStep(current.length, defaultTool)])} icon={<Plus aria-hidden className="h-3.5 w-3.5" />} className="self-start">Add step</Button>
        </fieldset>

        {serverError && <Alert tone="danger">The workflow wasn&apos;t saved: {serverError}</Alert>}
        <button type="submit" hidden aria-hidden tabIndex={-1} />
      </form>
    </Dialog>
  );
}
