"use client";

import { ArrowLeft, FileText, Heart, Info, Lightbulb, Pencil, Tag, Trash2, type LucideIcon } from "lucide-react";

import { AgentAvatar } from "@/components/agents/agent-avatar";
import { Button, IconButton } from "@/components/ui/button";
import { CopyButton } from "@/components/ui/copy-button";
import { Disclosure, JsonView } from "@/components/ui/disclosure";
import { kindLabel, wasEdited } from "@/lib/memory";
import { relativeTime } from "@/lib/operations";
import { cn } from "@/lib/utils";
import type { MemoryKind, MemoryRecord } from "@/types/memory";

// Kinds are told apart by icon and label, not by loud colours.
const KIND_ICONS: Record<MemoryKind, LucideIcon> = { fact: Lightbulb, note: FileText, preference: Heart, context: Info };

export function KindLabel({ kind, className }: { kind: MemoryKind; className?: string }) {
  const Icon = KIND_ICONS[kind] ?? FileText;
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground", className)}>
      <Icon aria-hidden className="h-3 w-3" />{kindLabel(kind)}
    </span>
  );
}

export function TagList({ tags, className }: { tags: readonly string[]; className?: string }) {
  if (tags.length === 0) return null;
  return (
    <ul aria-label="Tags" className={cn("flex flex-wrap gap-1.5", className)}>
      {tags.map((tag) => (
        <li key={tag} className="inline-flex min-w-0 max-w-full items-center gap-1 rounded border border-border bg-surface-2 px-1.5 py-0.5 text-[11px] text-muted-foreground">
          <Tag aria-hidden className="h-2.5 w-2.5 shrink-0" /><span className="truncate">{tag}</span>
        </li>
      ))}
    </ul>
  );
}

/** One row in the library: the content first, then kind, tags and when it last changed. */
export function MemoryRow({ record, selected, now, onSelect }: { record: MemoryRecord; selected: boolean; now: Date; onSelect: () => void }) {
  return (
    <li>
      <button type="button" data-memory-id={record.memory_id} onClick={onSelect} aria-current={selected ? "true" : undefined}
        className={cn("relative flex w-full flex-col gap-2 px-4 py-3.5 text-left transition-colors hover:bg-white/[0.025]", selected && "bg-white/[0.05]")}>
        {selected && <span aria-hidden className="absolute inset-y-3 left-0 w-0.5 rounded-full bg-accent" />}
        <span className="line-clamp-3 break-words text-sm leading-6 text-foreground">{record.content}</span>
        <span className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <KindLabel kind={record.kind} />
          <time dateTime={record.updated_at} title={`Last changed ${new Date(record.updated_at).toLocaleString()}`} className="text-[11px] text-subtle">
            {wasEdited(record) ? "Edited " : "Added "}{relativeTime(record.updated_at, now)}
          </time>
          <TagList tags={record.tags} />
        </span>
      </button>
    </li>
  );
}

/** The full record, read-only, with Edit and Delete. Technical details stay collapsed. */
export function MemoryDetail({ record, agentName, now, busy, onEdit, onDelete, onBack }: {
  record: MemoryRecord; agentName: string; now: Date; busy: boolean; onEdit: () => void; onDelete: () => void; onBack: () => void;
}) {
  return (
    <article aria-labelledby="memory-detail-title" className="flex min-w-0 flex-col gap-5">
      <header className="flex items-start gap-2">
        <IconButton label="Back to memories" onClick={onBack} className="-ml-1 lg:hidden"><ArrowLeft aria-hidden className="h-4 w-4" /></IconButton>
        <div className="min-w-0 flex-1">
          <h2 id="memory-detail-title" className="sr-only">Memory details</h2>
          <KindLabel kind={record.kind} className="text-sm text-foreground [&>svg]:h-4 [&>svg]:w-4" />
          <p className="mt-0.5 text-xs text-muted-foreground">
            {wasEdited(record) ? `Edited ${relativeTime(record.updated_at, now)} · added ${relativeTime(record.created_at, now)}` : `Added ${relativeTime(record.created_at, now)}`}
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button size="sm" onClick={onEdit} disabled={busy} icon={<Pencil aria-hidden className="h-3.5 w-3.5" />}>Edit</Button>
          <Button size="sm" variant="ghost" onClick={onDelete} disabled={busy} icon={<Trash2 aria-hidden className="h-3.5 w-3.5" />} className="text-danger hover:text-danger">Delete</Button>
        </div>
      </header>

      <p className="whitespace-pre-wrap break-words text-[15px] leading-7 text-foreground">{record.content}</p>

      <dl className="grid gap-3 border-t border-border pt-4 text-xs sm:grid-cols-2">
        <div className="min-w-0">
          <dt className="text-muted-foreground">Belongs to</dt>
          <dd className="mt-1 flex min-w-0 items-center gap-2 text-foreground"><AgentAvatar name={agentName} size="sm" /><span className="truncate">{agentName}</span></dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Tags</dt>
          <dd className="mt-1.5">{record.tags.length ? <TagList tags={record.tags} /> : <span className="text-foreground">None</span>}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Added</dt>
          <dd className="mt-1 text-foreground"><time dateTime={record.created_at}>{new Date(record.created_at).toLocaleString()}</time></dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Last changed</dt>
          <dd className="mt-1 text-foreground"><time dateTime={record.updated_at}>{new Date(record.updated_at).toLocaleString()}</time></dd>
        </div>
      </dl>

      <Disclosure summary="Technical details">
        <dl className="flex flex-col gap-3 text-xs">
          <div className="flex items-center justify-between gap-2">
            <dt className="text-muted-foreground">Memory ID</dt>
            <dd className="flex min-w-0 items-center gap-1"><span className="truncate font-mono text-[11px] text-foreground/90">{record.memory_id}</span><CopyButton value={record.memory_id} label="Copy memory ID" /></dd>
          </div>
          <div>
            <dt className="mb-1 text-muted-foreground">Metadata</dt>
            <dd>{Object.keys(record.metadata).length ? <JsonView value={record.metadata} /> : <span className="text-foreground">None</span>}</dd>
          </div>
        </dl>
      </Disclosure>
    </article>
  );
}
