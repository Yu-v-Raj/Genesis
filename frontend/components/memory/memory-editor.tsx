"use client";

import { FormEvent, useId, useRef, useState } from "react";
import { ChevronRight, Plus, Save } from "lucide-react";

import { AgentAvatar } from "@/components/agents/agent-avatar";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Alert } from "@/components/ui/feedback";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { MAX_CONTENT, MEMORY_KINDS, draftFrom, isDraftDirty, validateDraft, type DraftErrors, type MemoryDraft } from "@/lib/memory";
import { cn } from "@/lib/utils";
import type { CreateMemoryInput, MemoryKind, MemoryRecord } from "@/types/memory";

/**
 * Add or edit one memory. Same fields and payload as before (content, kind, tags,
 * metadata). The owning Agent is shown but can't be changed: memories never move between
 * Agents. A failed save keeps the edits; closing with unsaved edits asks first.
 */
export function MemoryEditor({ record, agentName, onClose, onSubmit }: {
  /** `null` adds a new memory. */
  record: MemoryRecord | null;
  agentName: string;
  onClose: () => void;
  /** Resolves to an error message, or `null` on success. */
  onSubmit: (input: CreateMemoryInput) => Promise<string | null>;
}) {
  const editing = record !== null;
  const ids = useId();
  const [initial] = useState<MemoryDraft>(() => draftFrom(record));
  const [draft, setDraft] = useState<MemoryDraft>(initial);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const inFlight = useRef(false);
  const contentRef = useRef<HTMLTextAreaElement>(null);
  const metadataRef = useRef<HTMLTextAreaElement>(null);
  const dirty = isDraftDirty(draft, initial);
  const length = draft.content.trim().length;

  function set<K extends keyof MemoryDraft>(key: K, value: MemoryDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
    if (key in errors) setErrors((current) => ({ ...current, [key]: undefined }));
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
    const result = validateDraft(draft);
    if (result.errors) {
      setErrors(result.errors);
      (result.errors.content ? contentRef : metadataRef).current?.focus();
      return;
    }
    inFlight.current = true;
    setSubmitting(true);
    setServerError(null);
    try {
      const failure = await onSubmit(result.input);
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
      <p className="text-sm text-foreground">Discard your unsaved changes?</p>
      <div className="flex gap-2 sm:justify-end">
        <Button size="sm" onClick={() => setConfirmDiscard(false)} autoFocus>Keep editing</Button>
        <Button size="sm" variant="danger" onClick={onClose}>Discard</Button>
      </div>
    </div>
  ) : (
    <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
      <Button onClick={requestClose} disabled={submitting}>Cancel</Button>
      <Button type="submit" form={formId} variant="primary" loading={submitting} disabled={editing && !dirty}
        icon={editing ? <Save aria-hidden className="h-4 w-4" /> : <Plus aria-hidden className="h-4 w-4" />}>
        {submitting ? "Saving…" : editing ? "Save changes" : "Add memory"}
      </Button>
    </div>
  );

  return (
    <Dialog open onClose={requestClose} size="lg" footer={footer}
      title={editing ? "Edit memory" : "Add memory"}
      description={editing ? "Change what this Agent remembers. It uses the updated text from its next message." : "Save something this Agent should remember. It's included with every message the Agent receives."}>
      <form id={formId} onSubmit={submit} noValidate className="flex flex-col gap-5">
        <div className="flex items-center gap-2.5 rounded-md border border-border bg-surface-2/60 px-3 py-2">
          <AgentAvatar name={agentName} size="sm" />
          <p className="min-w-0 text-xs text-muted-foreground">
            {editing ? "Belongs to" : "For"} <span className="font-medium text-foreground">{agentName}</span>
            <span className="block text-[11px]">Only this Agent can see it.</span>
          </p>
        </div>

        <Field
          label={<>What should it remember? <span className="text-danger" aria-hidden>*</span><span className="sr-only">(required)</span></>}
          error={errors.content}
          hint={<span className={cn("tabular-nums", length > MAX_CONTENT && "text-danger")}>{length.toLocaleString("en-US")} / {MAX_CONTENT.toLocaleString("en-US")} characters. Don&apos;t store passwords or API keys.</span>}
        >
          {(props) => <Textarea {...props} ref={contentRef} value={draft.content} onChange={(event) => set("content", event.target.value)} rows={6} placeholder="e.g. The user's project is called Atlas and launches on 1 March." data-autofocus className="min-h-36" />}
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Kind" hint={MEMORY_KINDS.find((kind) => kind.value === draft.kind)?.description}>
            {(props) => (
              <Select {...props} value={draft.kind} onChange={(event) => set("kind", event.target.value as MemoryKind)}>
                {MEMORY_KINDS.map((kind) => <option key={kind.value} value={kind.value}>{kind.label}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Tags" hint="Comma separated, for example: project, launch.">
            {(props) => <Input {...props} value={draft.tags} onChange={(event) => set("tags", event.target.value)} placeholder="project, launch" autoComplete="off" />}
          </Field>
        </div>

        <details className="group rounded-md border border-border" open={Boolean(errors.metadata) || undefined}>
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground [&::-webkit-details-marker]:hidden">
            <ChevronRight aria-hidden className="h-4 w-4 transition-transform group-open:rotate-90" />
            Metadata <span className="text-xs">(optional, advanced)</span>
          </summary>
          <div className="border-t border-border p-3">
            <Field label="Metadata (JSON object)" error={errors.metadata} hint="Extra structured details stored with the memory. Leave empty for none.">
              {(props) => <Textarea {...props} ref={metadataRef} value={draft.metadata} onChange={(event) => set("metadata", event.target.value)} rows={3} placeholder={'{"source": "operator"}'} spellCheck={false} className="min-h-20 font-mono text-xs" />}
            </Field>
          </div>
        </details>

        {serverError && <Alert tone="danger">{editing ? "Your changes weren't saved" : "The memory wasn't added"}: {serverError}</Alert>}
        <button type="submit" hidden aria-hidden tabIndex={-1} />
      </form>
    </Dialog>
  );
}
