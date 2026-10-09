"use client";

import { useId, useState } from "react";
import { AlertTriangle, LoaderCircle, RotateCcw } from "lucide-react";

import { retryPresentation } from "@/lib/durable-work";
import type { RetryInfo } from "@/types/executions";

/**
 * Retry button driven entirely by the server's decision. When the server says the work
 * may already have had external effects, the user must tick a confirmation first; the
 * server enforces the same rule, so this is guidance, not the authorization boundary.
 */
export function RetryControl({ retry, onRetry }: { retry: RetryInfo | null; onRetry: (acknowledgeSideEffects: boolean) => Promise<string | null> }) {
  const id = useId();
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const presentation = retryPresentation(retry);
  if (!presentation.visible) return null;

  async function submit() {
    if (pending) return;
    setPending(true);
    setError(null);
    const failure = await onRetry(presentation.needsConfirmation && confirmed);
    setPending(false);
    if (failure) setError(failure);
    else setConfirmed(false);
  }

  return (
    <div className={`rounded-lg border p-3 text-xs ${presentation.needsConfirmation ? "border-amber-400/25 bg-amber-400/5" : "border-border bg-background/40"}`}>
      <p className={`flex items-start gap-2 leading-5 ${presentation.needsConfirmation ? "text-amber-100" : "text-muted-foreground"}`}>
        {presentation.needsConfirmation && <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
        {presentation.explanation}
      </p>
      {presentation.needsConfirmation && (
        <label htmlFor={`${id}-confirm`} className="mt-2 flex items-center gap-2 text-amber-100">
          <input id={`${id}-confirm`} type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} className="accent-primary" />
          I understand this may repeat an external action.
        </label>
      )}
      <button
        type="button"
        onClick={() => void submit()}
        disabled={pending || (presentation.needsConfirmation && !confirmed)}
        className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 font-medium text-foreground transition-colors hover:bg-white/[0.06] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {pending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />}
        {pending ? "Retrying…" : presentation.label}
      </button>
      {error && <p role="alert" className="mt-2 text-red-200">{error}</p>}
    </div>
  );
}
