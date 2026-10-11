# Durable Executions and Workflows (v0.12)

Executions and workflow runs are stored in the database named by `DATABASE_URL`, so the
work Genesis does can be inspected after a restart, and work that a crash interrupted is
either resumed safely or held for a person to decide. This document states exactly what
is guaranteed and what is not.

## Concepts

| Concept | What it is | Stored in |
|---|---|---|
| Execution | One unit of Agent work: a chat turn (v0.13), a tool call, or the deterministic placeholder | `executions`, `execution_transitions` |
| Workflow definition | A reusable, versioned plan of tool steps and dependencies | `workflow_definitions` (one row per version) |
| Workflow run | One attempt to carry out one definition version | `workflow_runs` |
| Workflow step | One step of a run, with its own state, result, and error | `workflow_run_steps` |

An Agent's lifecycle (`CREATED → INITIALIZING → IDLE ↔ RUNNING`) is separate: running an
execution never changes the Agent's status.

## Execution state machine

```text
PENDING → QUEUED → STARTING → RUNNING → COMPLETED | FAILED
             ↑         │          └──→ INTERRUPTED   (process lost mid-work)
             └─────────┘  recovery: claimed but never started → back to QUEUED
any non-terminal → CANCELLED
```

- `STARTING`: a worker has claimed the execution but has not begun the work.
- `RUNNING` is written **before** the work is invoked. From that moment an interruption
  means the outcome is unknown.
- Terminal states (`COMPLETED`, `FAILED`, `CANCELLED`, `INTERRUPTED`) never change. A
  retry creates a **new execution** with `attempt = n + 1` and `retry_of` pointing at the
  original, so history is never rewritten.
- Every transition is a compare-and-set on a `version` column and appends a row to
  `execution_transitions` in the same transaction (`GET /api/executions/{id}/history`).
  A stale writer (for example a late completion after a cancel) is rejected instead of
  overwriting newer state.

## Workflow run and step state machines

```text
Run:  CREATED → QUEUED → RUNNING ↔ PAUSED
                          ├→ COMPLETED                      (final)
                          ├→ FAILED       ──retry──→ QUEUED
                          ├→ INTERRUPTED  ──retry──→ QUEUED  (needs a decision)
                          └→ QUEUED                          (recovery, nothing uncertain)
      any non-final → CANCELLED                              (final)

Step: PENDING → READY → RUNNING → COMPLETED | FAILED
      dependents of a failed step → BLOCKED
      running when the process stopped → INTERRUPTED (or back to PENDING if side-effect free)
```

- A step is stored as `RUNNING` **before** its tool is called and as `COMPLETED`/`FAILED`
  after, in the same transaction as the run's status (compare-and-set on the run's
  `version`).
- Retrying a run resumes **the same run**: `FAILED`, `BLOCKED`, `CANCELLED`, and
  `INTERRUPTED` steps go back to `PENDING`; `COMPLETED` steps are kept and never re-run.
  The run's `attempt` increments.
- Definitions are immutable per version. `PUT /api/workflow-definitions/{id}` stores a
  new version; a run always keeps the steps it was created with.

## Chat turns as executions (v0.13)

Every `POST /api/agents/{id}/chat` is a durable execution with
`metadata = {"kind": "chat", "message": ..., "session_id": ...}`, run by the same worker as
all other work through a registered `WorkHandler` (`agent_runtime/application/chat_work.py`).

```text
Agent (long-lived)  ─┬─ Session (conversation) ── messages tagged with interaction_id
                     └─ Execution (one chat turn) ── execution_id == interaction_id
                          ├─ timeline: queued → starting → running → checkpoint: tool:X → completed
                          ├─ checkpoint: tools_started [{name, call_id, side_effects}]
                          └─ Tool Runtime tasks with execution_id
```

- The request is checked first (model, Agent available, session belongs to the Agent);
  rejected requests create no execution. The session is fixed when the request is made.
- The HTTP request waits for the execution; if the client disconnects the turn still
  finishes and is saved. The response adds `execution_id` (equal to `interaction_id`).
- The Agent lifecycle is unchanged: the turn moves the Agent IDLE → RUNNING → IDLE, and
  the execution records the outcome. Cancelling a running chat stops the work and always
  returns the Agent to IDLE.
- Before each approved tool call a checkpoint records the tool's name, call ID, and
  declared side effects (never its arguments or provider metadata such as Gemini thought
  signatures). Failures get a category: `configuration`, `timeout`, `provider_error`,
  `agent_unavailable`, `invalid_request`, `conflict`, `storage`, or `chat_failed`.

Recovery after a crash, from stored evidence:

| Found | Decision |
|---|---|
| Queued / claimed-not-started chat | Runs after restart; its reply is saved to the session. |
| Running chat whose turn **is** in the session (messages tagged with its ID) | `COMPLETED` — only marking it done was lost. Never re-run. |
| Running chat, no saved turn, no side-effecting tool started | `INTERRUPTED`; retry allowed without confirmation (the model may be called again). |
| Running chat, no saved turn, a side-effecting tool had started | `INTERRUPTED`; retry requires `acknowledge_side_effects`. |

A retry is a new execution with the same message; because turns are saved atomically and
a finished chat cannot be retried, retries never duplicate a saved turn. The Agents page
lists a session's unfinished messages with their reason and a server-gated Retry.

## Queue and workers

The database is the queue; there is no separate broker.

- A worker **claims** work with a conditional update (`QUEUED → STARTING` for executions,
  `QUEUED → RUNNING` for runs). Only one worker can win a claim, even across processes.
- The claim carries a **lease** (`lease_owner`, `lease_expires_at`, default 30 s,
  `WORKER_LEASE_SECONDS`). The worker renews it every third of the lease while it works.
- Each process works on at most `WORKER_CONCURRENCY` executions and the same number of
  runs (default 4).
- A row that says `RUNNING` is **not** proof that a worker is alive; an unexpired lease
  is. Recovery only touches rows whose lease has expired, so a second process never
  steals work a live worker still holds.
- Shutdown stops claiming, gives running work a few seconds, then cancels the rest:
  executions are recorded as `INTERRUPTED` immediately; workflow steps are resolved by
  recovery on the next start once their lease expires.

## Recovery and guarantees

Recovery runs at startup and on every worker tick.

| Found after a crash | What Genesis does |
|---|---|
| `QUEUED` execution or run | Runs it. Nothing had started. |
| `STARTING` execution (claimed, not begun) | Returns it to `QUEUED` and runs it (`execution.recovered`). |
| `RUNNING` execution | Marks it `INTERRUPTED` (`execution.interrupted`). Never re-run automatically. |
| Run with a `RUNNING` step whose tool is side-effect free | Step back to `PENDING`; run requeued and resumed (`workflow.recovered`). |
| Run with a `RUNNING` step whose tool may have side effects | Step `INTERRUPTED`, run `INTERRUPTED` (`workflow.interrupted`); waits for a person. |
| `COMPLETED` steps | Kept. Never re-run, by recovery or by retry. |

**Side effects.** Each tool declares `side_effects` (`ToolMetadata.side_effects`,
exposed by `GET /api/tools`). It defaults to `True`: an unknown or unregistered tool is
assumed to have effects. All current built-in tools are side-effect free.

**What is guaranteed:**

- Side-effect-free work is effectively *at-least-once*: if a crash cuts it off it may run
  again, which is harmless by definition.
- Work that may have side effects is *at-most-once automatically*: after a crash it is
  never repeated without a person. Retrying an interrupted side-effecting execution or
  step requires `"acknowledge_side_effects": true`; without it the API returns `409`
  with the reason. The UI shows the reason and asks for an explicit confirmation.

**What is not guaranteed:** exactly-once execution of external actions. A crash can land
after an external system acted but before Genesis recorded it; Genesis then reports the
outcome as unknown rather than guessing. Tools that need stronger guarantees should use
an idempotency key: workflow tool calls receive `workflow_id`, `workflow_task_id`, and
`workflow_attempt` in their request metadata, and executions have a stable
`execution_id`. No built-in tool implements idempotency keys yet.

## Events

State is written first, then the event is published (`execution.*`, `workflow.*`,
including `execution.interrupted`, `execution.recovered`, `workflow.interrupted`,
`workflow.recovered`, `workflow.retried`, `workflow.task.interrupted`,
`workflow.definition.created|updated`). Events are best-effort notifications: if the
process dies between the commit and the publish, the event is lost but the stored state
is correct, and clients that reconnect reload state over REST. There is deliberately no
transactional outbox yet; the database, not the event stream, is the source of truth.

## API

Executions:

- `POST /api/agents/{id}/execute` — queue work (202).
- `GET /api/executions`, `GET /api/executions/{id}`, `GET /api/agents/{id}/executions`.
- `GET /api/executions/{id}/history` — the durable timeline.
- `POST /api/executions/{id}/cancel`.
- `POST /api/executions/{id}/retry` `{"acknowledge_side_effects": false}` — new attempt (202).

Every execution response includes `attempt`, `retry_of`, `error_category`, and `retry`
(`allowed`, `requires_acknowledgement`, `reason`) computed by the server. Lease internals
are not exposed.

Workflows:

- `POST/GET /api/workflow-definitions`, `GET/PUT /api/workflow-definitions/{id}`
  (`?version=` to read an older version).
- `POST /api/workflow-definitions/{id}/runs` `{"version": null, "start": true}`.
- `POST /api/workflows` (define + create a run, as before), `GET /api/workflows`,
  `GET/DELETE /api/workflows/{id}`, `POST /api/workflows/{id}/start|pause|resume|cancel`,
  `POST /api/workflows/{id}/retry`, `GET /api/workflows/{id}/tasks|history`.

## Inspecting and recovering work

- **Monitoring → Executions** lists recent executions; open one to see its timeline,
  error category, and a Retry control when the server allows it.
- **Workflows** lists saved definitions (Run starts a new run) and runs; a failed or
  interrupted run shows why and offers Retry (with confirmation when a step may already
  have had external effects).
- An interrupted run can also be cancelled if the work should not be repeated.

## Limitations

- No authentication or authorization: anyone who can reach the API can start, cancel,
  or retry work.
- Workflows are not bound to an Agent, so Agent tool allowlists do not apply to workflow
  steps; Tool Runtime still only runs registered, enabled tools. Agent chat tool calls
  remain gated by the Agent safety gate.
- Cancelling work held by another process marks it cancelled in storage, but only the
  owning process can stop its in-flight task; that process's later write is rejected.
- `PAUSED` workflows pause dispatch only; a step already running finishes.
- Chat turns share the worker pool (`WORKER_CONCURRENCY`) with other executions, so a
  burst of long tool work can delay chat replies.
- A model call cut off by a crash may be repeated by a retry, which can cost provider
  tokens twice; model calls themselves change nothing outside Genesis.
- Agents and sessions are cached per process (see `20-Agent-Persistence.md`), so running
  several backend processes is not supported yet even though work claiming is safe.
- Tool task history (`/api/tools/history`), memory records, and the event stream are
  still in memory.
