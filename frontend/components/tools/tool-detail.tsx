"use client";

import { FormEvent, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, FlaskConical, Play, ShieldAlert, ShieldCheck } from "lucide-react";

import { AgentAvatar } from "@/components/agents/agent-avatar";
import { ToolRunRow } from "@/components/tools/tool-run";
import { Button, IconButton } from "@/components/ui/button";
import { Disclosure, JsonView } from "@/components/ui/disclosure";
import { Alert } from "@/components/ui/feedback";
import { Field, Input } from "@/components/ui/field";
import { StatusBadge } from "@/components/ui/status-badge";
import type { TestRunResult } from "@/hooks/use-tools";
import { agentsAllowing, buildArguments, declaredPermissions, tasksForTool, testFieldsFor, toolLabel } from "@/lib/tools";
import type { Agent } from "@/types/agents";
import type { ToolDefinition, ToolTask } from "@/types/tools";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t border-border pt-4">
      <h3 className="text-xs font-medium uppercase tracking-wider text-subtle">{title}</h3>
      {children}
    </section>
  );
}

/** Everything about one tool. Opening it never runs anything. */
export function ToolDetail({ tool, agents, tasks, now, pending, onRun, onBack }: {
  tool: ToolDefinition;
  agents: readonly Agent[];
  tasks: readonly ToolTask[];
  now: Date;
  pending: boolean;
  onRun: (arguments_: Record<string, unknown>) => Promise<TestRunResult>;
  onBack: () => void;
}) {
  const fields = testFieldsFor(tool.name);
  const allowed = agentsAllowing(tool, agents);
  const permissions = declaredPermissions(tool);
  const runs = tasksForTool(tasks, tool.name);

  return (
    <article aria-labelledby="tool-detail-title" className="flex min-w-0 flex-col gap-4">
      <header className="flex items-start gap-2">
        <IconButton label="Back to tools" onClick={onBack} className="-ml-1 lg:hidden"><ArrowLeft aria-hidden className="h-4 w-4" /></IconButton>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="tool-detail-title" className="text-base font-semibold text-foreground">{toolLabel(tool.name)}</h2>
            <StatusBadge status={tool.enabled ? "ready" : "disabled"} label={tool.enabled ? "Enabled" : "Disabled"} />
          </div>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">{tool.description}</p>
        </div>
      </header>

      <Section title="What it needs">
        {fields === undefined ? (
          <p className="text-sm text-muted-foreground">The server defines this tool&apos;s inputs, but the API doesn&apos;t publish them yet.</p>
        ) : fields.length === 0 ? (
          <p className="text-sm text-foreground">Nothing — it takes no inputs.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {fields.map((field) => (
              <li key={field.name} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <code className="rounded border border-border bg-surface-2 px-1 font-mono text-xs text-foreground">{field.name}</code>
                <span className="text-xs text-muted-foreground">{field.integer ? "whole number" : field.type}, required</span>
                <span className="w-full text-xs text-muted-foreground">{field.helper}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Who can use it">
        {!tool.enabled ? (
          <p className="text-sm text-foreground">No one: the tool is disabled on the server, so it never runs.</p>
        ) : allowed.length === 0 ? (
          <p className="text-sm text-muted-foreground">No Agent is allowed to use it yet. Allow it in an Agent&apos;s settings.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {allowed.map((agent) => (
              <li key={agent.id}>
                <Link href={`/agents?agent=${agent.id}`} className="inline-flex max-w-56 items-center gap-2 rounded-md border border-border bg-surface-2 py-1 pl-1 pr-2.5 text-xs text-foreground hover:border-border-strong">
                  <AgentAvatar name={agent.name} size="sm" /><span className="truncate">{agent.name}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[11px] leading-4 text-subtle">An Agent can only call tools allowed in its settings; the server checks every call.</p>
      </Section>

      <Section title="Restrictions">
        <p className="flex items-start gap-2 text-sm text-foreground">
          {tool.side_effects
            ? <><ShieldAlert aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-warning" />May change things outside Genesis. If a run that used it is interrupted, retrying asks for confirmation first.</>
            : <><ShieldCheck aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-success" />Declared as having no effects outside Genesis.</>}
        </p>
        <p className="text-xs leading-5 text-muted-foreground">
          {permissions.length
            ? <>Declares permissions: {permissions.join(", ")}. Permission rules are declared for future enforcement; today, access is controlled per Agent.</>
            : <>Declares no special permissions. (Permission rules are declared for future enforcement; today, access is controlled per Agent.)</>}
        </p>
      </Section>

      <Section title={`Recent runs${runs.length ? ` (${runs.length})` : ""}`}>
        {runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No runs recorded since the backend started.</p>
        ) : (
          <ul className="-mx-4 divide-y divide-border border-y border-border">{runs.slice(0, 10).map((task) => <ToolRunRow key={task.task_id} task={task} now={now} />)}</ul>
        )}
      </Section>

      <Disclosure summary={<span className="inline-flex items-center gap-1.5"><FlaskConical aria-hidden className="h-3.5 w-3.5" />Run a test</span>}>
        <TestRun tool={tool} fields={fields} pending={pending} onRun={onRun} />
      </Disclosure>

      <Disclosure summary="Technical details">
        <dl className="grid grid-cols-[7rem_minmax(0,1fr)] gap-x-3 gap-y-2 text-xs">
          <dt className="text-muted-foreground">Name</dt><dd className="font-mono text-foreground">{tool.name}</dd>
          <dt className="text-muted-foreground">Version</dt><dd className="font-mono text-foreground">{tool.version}</dd>
          <dt className="text-muted-foreground">Capabilities</dt><dd className="break-words font-mono text-foreground">{tool.capabilities.join(", ") || "—"}</dd>
          <dt className="text-muted-foreground">Permissions</dt><dd className="font-mono text-foreground">{tool.permissions.join(", ") || "—"}</dd>
          <dt className="text-muted-foreground">Side effects</dt><dd className="font-mono text-foreground">{String(tool.side_effects)}</dd>
          <dt className="text-muted-foreground">Metadata</dt><dd>{Object.keys(tool.metadata).length ? <JsonView value={tool.metadata} /> : <span className="text-foreground">None</span>}</dd>
        </dl>
      </Disclosure>
    </article>
  );
}

/**
 * An operator test: one explicit run on the Genesis server through the Tool Runtime (the
 * same validation as Agent calls, but outside any Agent). Never runs on open.
 */
function TestRun({ tool, fields, pending, onRun }: { tool: ToolDefinition; fields: ReturnType<typeof testFieldsFor>; pending: boolean; onRun: (arguments_: Record<string, unknown>) => Promise<TestRunResult> }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [outcome, setOutcome] = useState<TestRunResult | null>(null);
  const inFlight = useRef(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current || !fields || !tool.enabled) return;
    const built = buildArguments(fields, values);
    if (built.errors) { setErrors(built.errors); return; }
    setErrors({});
    inFlight.current = true;
    try {
      setOutcome(await onRun(built.arguments));
    } finally {
      inFlight.current = false;
    }
  }

  if (!tool.enabled) return <p className="text-sm text-muted-foreground">Disabled tools can&apos;t be run.</p>;
  if (fields === undefined) return <p className="text-sm text-muted-foreground">This page doesn&apos;t know this tool&apos;s inputs, so it can&apos;t offer a test run.</p>;

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-3">
      <p className="text-xs leading-5 text-muted-foreground">
        Runs the tool once on the Genesis server, outside any Agent. The server validates the inputs and records the run under Recent runs.
        {tool.side_effects && <strong className="font-medium text-warning"> This tool may change things outside Genesis.</strong>}
      </p>
      {fields.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {fields.map((field) => (
            <Field key={field.name} label={field.label} hint={field.helper} error={errors[field.name]}>
              {(props) => <Input {...props} type={field.type} inputMode={field.type === "number" ? "decimal" : undefined} value={values[field.name] ?? ""}
                onChange={(event) => { setValues((current) => ({ ...current, [field.name]: event.target.value })); setErrors((current) => ({ ...current, [field.name]: "" })); }}
                placeholder={field.placeholder} min={field.min} max={field.max} disabled={pending} autoComplete="off" />}
            </Field>
          ))}
        </div>
      )}
      <div>
        <Button type="submit" size="sm" loading={pending} icon={<Play aria-hidden className="h-3.5 w-3.5" />}>{pending ? "Running…" : "Run test"}</Button>
      </div>
      <div aria-live="polite">
        {outcome && (outcome.task ? (
          <div className="flex flex-col gap-2 rounded-md border border-border bg-surface-2/60 p-3">
            <div className="flex items-center gap-2 text-xs"><StatusBadge status={outcome.task.result?.status ?? outcome.task.status} /><span className="text-muted-foreground">Result</span></div>
            {outcome.task.result?.error && <p className="break-words text-xs text-danger">{outcome.task.result.error}</p>}
            {outcome.task.result && outcome.task.result.output !== null && <JsonView value={outcome.task.result.output} />}
          </div>
        ) : (
          <Alert tone="danger">The server didn&apos;t run it: {outcome.error}</Alert>
        ))}
      </div>
    </form>
  );
}
