"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Plus, X } from "lucide-react";

import type { CreateAgentInput } from "@/types/agents";

interface CreateAgentDialogProps {
  open: boolean;
  pending: boolean;
  onClose: () => void;
  onSubmit: (input: CreateAgentInput) => Promise<boolean>;
}

export function CreateAgentDialog({
  open,
  pending,
  onClose,
  onSubmit,
}: CreateAgentDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("");
  const [tags, setTags] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    nameInputRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !pending) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open, pending]);

  if (!open) return null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !description.trim() || !type.trim()) {
      setValidationError("Name, description, and type are required.");
      return;
    }
    setValidationError(null);
    const created = await onSubmit({
      name: name.trim(),
      description: description.trim(),
      type: type.trim(),
      tags: tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    });
    if (!created) return;
    setName("");
    setDescription("");
    setType("");
    setTags("");
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" role="presentation">
      <form
        className="w-full max-w-lg rounded-xl border border-border bg-surface p-5 shadow-2xl shadow-black/40 sm:p-6"
        onSubmit={submit}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-agent-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="create-agent-title" className="text-lg font-semibold tracking-tight text-foreground">
              Create Agent
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Create a runtime record now; you can start execution when it&apos;s ready.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-white/5 hover:text-foreground disabled:opacity-50"
            aria-label="Close create agent dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-6 grid gap-5">
          <Field label="Name" value={name} onChange={setName} inputRef={nameInputRef} placeholder="e.g. Research companion" helper="A clear, recognizable name for this agent." />
          <Field label="Description" value={description} onChange={setDescription} multiline placeholder="Describe this agent's role and expected output." helper="This helps teammates understand the agent at a glance." />
          <Field label="Type" value={type} onChange={setType} placeholder="e.g. planning" helper="Used to categorize the agent and select its icon." />
          <Field label="Tags" value={tags} onChange={setTags} placeholder="e.g. product, research" helper="Optional. Separate tags with commas." />
        </div>

        {validationError && <p role="alert" className="mt-5 rounded-lg border border-red-400/20 bg-red-400/10 px-3 py-2 text-sm text-red-200">{validationError}</p>}

        <div className="mt-7 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:bg-white/5 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={pending}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" /> {pending ? "Creating..." : "Create Agent"}
          </button>
        </div>
        <p className="mt-4 text-center text-xs text-muted-foreground">Press <kbd className="rounded border border-border bg-background px-1 py-0.5">Enter</kbd> to create or <kbd className="rounded border border-border bg-background px-1 py-0.5">Esc</kbd> to close.</p>
      </form>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  helper,
  multiline = false,
  inputRef,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  helper?: string;
  multiline?: boolean;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}) {
  const className = "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 hover:border-white/15 focus:border-primary";
  return (
    <label className="grid gap-1.5 text-sm font-medium text-foreground">
      {label}
      {multiline ? (
        <textarea value={value} onChange={(event) => onChange(event.target.value)} rows={3} placeholder={placeholder} className={className} />
      ) : (
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          ref={inputRef}
          className={className}
        />
      )}
      {helper && <span className="text-xs font-normal leading-5 text-muted-foreground">{helper}</span>}
    </label>
  );
}
