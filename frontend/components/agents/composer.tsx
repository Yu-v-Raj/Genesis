"use client";

import { useLayoutEffect, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { ArrowUp, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const MAX_HEIGHT = 200;

/**
 * The message box. Enter sends and Shift+Enter adds a line (IME composition is respected).
 * It stays editable while a reply is pending so the next message can be drafted, but a
 * second message can't be sent until the first finishes.
 */
export function Composer({ value, onChange, onSubmit, inputRef, agentName, disabledReason, pending }: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  inputRef: RefObject<HTMLTextAreaElement | null>;
  agentName: string;
  /** Set when the Agent can't chat; shown as the placeholder and disables the box. */
  disabledReason: string | null;
  pending: boolean;
}) {
  const canSend = disabledReason === null && !pending && value.trim().length > 0;

  // Grow with the content up to a limit, then scroll inside the box.
  useLayoutEffect(() => {
    const element = inputRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT)}px`;
  }, [value, inputRef]);

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (canSend) onSubmit();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-3xl">
      <div className={cn("flex items-end gap-2 rounded-lg border bg-surface-2 p-2 transition-colors focus-within:border-accent/70", disabledReason ? "border-border opacity-70" : "border-border-strong")}>
        <label htmlFor="agent-composer" className="sr-only">Message {agentName}</label>
        <textarea
          id="agent-composer"
          ref={inputRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          disabled={disabledReason !== null}
          rows={1}
          enterKeyHint="send"
          placeholder={disabledReason ?? `Message ${agentName}…`}
          aria-describedby="agent-composer-hint"
          className="max-h-[200px] min-h-9 min-w-0 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-6 text-foreground outline-none placeholder:text-subtle disabled:cursor-not-allowed"
        />
        <button type="submit" disabled={!canSend} aria-label={pending ? "Sending" : "Send message"}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent text-accent-foreground transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:bg-white/[0.08] disabled:text-subtle">
          {pending ? <LoaderCircle aria-hidden className="h-4 w-4 animate-spin" /> : <ArrowUp aria-hidden className="h-4 w-4" />}
        </button>
      </div>
      <p id="agent-composer-hint" className="mt-1.5 hidden px-1 text-[11px] text-subtle sm:block">
        {pending ? `${agentName} is replying — you can draft your next message.` : "Enter to send · Shift+Enter for a new line"}
      </p>
    </form>
  );
}
