# Genesis — Agent Runtime

## 1. Purpose

This document defines the Runtime subsystem: the component of the Agent OS responsible for actually executing agents according to the lifecycle defined in `05-Agent-OS.md`, Section 4. Where `05-Agent-OS.md` establishes *what* the lifecycle states mean conceptually, this document defines *how* the Runtime implements, schedules, and enforces that lifecycle in practice.

This document assumes familiarity with `02-System-Architecture.md` (layering and dependency rules) and `05-Agent-OS.md` (Agent OS philosophy and lifecycle). It remains application-agnostic: nothing here may reference a specific application's domain logic.

## 2. Role of the Runtime Within the Agent OS

The Runtime is the execution engine of the Agent OS. It does not decide *what* an agent should do — that is defined by the Workflow Engine's graph (see `02-System-Architecture.md`, Section 5.2) and, ultimately, by the Application. The Runtime decides *how* execution proceeds: when an agent runs, how its state is persisted, how it is paused and resumed, how errors are handled, and how checkpoints (tool calls, approvals) are enforced.

```
Workflow Engine  ──defines──▶  Workflow Graph (what to execute)
                                     │
                                     ▼
Runtime          ──executes───▶  Agent Execution (how it's executed)
```

## 3. Runtime Architecture

The Runtime is composed of four internal components, each with a narrow responsibility:

```
┌─────────────────────────────────────────────────────────────┐
│                          Runtime                              │
│                                                                │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐   │
│  │   Scheduler    │  │  Execution     │  │  State           │   │
│  │                │  │  Context        │  │  Persistence     │   │
│  │                │  │  Manager        │  │  Manager         │   │
│  └───────┬───────┘  └───────┬───────┘  └────────┬─────────┘   │
│          │                   │                    │             │
│          └───────────┬───────┴────────────────────┘             │
│                       ▼                                          │
│              ┌─────────────────┐                                 │
│              │  Lifecycle       │                                 │
│              │  Controller       │                                 │
│              └─────────────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

| Component | Responsibility |
|---|---|
| Scheduler | Decides when and in what order pending agent executions are run, subject to concurrency and resource limits |
| Execution Context Manager | Constructs and tears down the isolated context (memory handles, tool access, identity) an agent executes within |
| State Persistence Manager | Persists lifecycle state and execution checkpoints so execution can be paused, resumed, or recovered after failure |
| Lifecycle Controller | Enforces valid lifecycle-state transitions (per `05-Agent-OS.md`, Section 4) and routes transitions to the Approval Gateway or Tool Manager as required |

Each component is accessed only through the Runtime's own internal interfaces; none is exposed directly to Applications. Applications interact with the Runtime exclusively through the `runtime_contract` defined in `core/contracts/` (see `04-Folder-Structure.md`, Section 4).

## 4. Execution Lifecycle

The Runtime enforces the lifecycle states defined conceptually in `05-Agent-OS.md`, Section 4. This section defines the concrete transition rules the Lifecycle Controller enforces.

### 4.1 State Transition Table

| From | To | Trigger |
|---|---|---|
| Created | Running | Scheduler admits the execution based on available capacity |
| Running | Waiting on Tool | Agent invokes a tool via the Tool Manager |
| Running | Awaiting Approval | Agent attempts an action classified as important |
| Running | Paused | Explicit pause request (application-initiated or system-initiated, e.g. shutdown) |
| Running | Completed | Workflow graph reaches a terminal success node |
| Running | Failed | Unrecoverable error encountered during execution |
| Waiting on Tool | Running | Tool Manager returns a result |
| Awaiting Approval | Running | Approval Gateway records an approval decision |
| Awaiting Approval | Failed | Approval Gateway records a rejection decision |
| Paused | Running | Explicit resume request |

Any transition not listed in this table is invalid and is rejected by the Lifecycle Controller. This is a deliberate constraint: it guarantees that no execution path — regardless of which Application defined the workflow — can reach an unaccounted-for state.

### 4.2 Checkpointing

Every transition in Section 4.1 is accompanied by a persisted checkpoint written by the State Persistence Manager, containing:

- The workflow graph position (which node the execution is at)
- The agent's working memory reference (see `07-Memory-System.md`)
- The triggering event (tool call, approval request, pause request)
- A timestamp and execution identifier

Checkpointing is what makes Paused executions resumable even across process restarts, and what makes Failed executions diagnosable after the fact (see Section 7).

## 5. Scheduling

### 5.1 Scheduling Model

The Scheduler admits Created executions into the Running state based on:

- **Concurrency limits** — a configurable maximum number of concurrently Running executions, preventing unbounded resource consumption.
- **Fairness** — executions are admitted in a manner that prevents any single Application or agent type from starving others of Runtime capacity.
- **Priority hints** — Applications may attach a priority hint to a submitted task; the Scheduler uses this only as an ordering signal among otherwise-eligible executions, never as a bypass of concurrency limits or the lifecycle itself.

### 5.2 Long-Running and Resumable Execution

Because agent tasks may involve long-running tool calls or extended waits for human approval, the Scheduler does not hold a dedicated worker idle for a Waiting on Tool or Awaiting Approval execution. Instead, the Execution Context Manager releases the underlying compute resource while the State Persistence Manager retains the checkpoint, and the Scheduler re-admits the execution once its blocking condition resolves (tool result returned, approval decision recorded). This is what allows Genesis to support many more concurrently *pending* executions than concurrently *actively computing* ones.

## 6. Communication Flow

The Runtime does not implement inter-agent communication itself; it delegates to the Communication Layer (`02-System-Architecture.md`, Section 5.2) while enforcing that all communication occurs within a tracked execution context.

```
Agent A (Running)                         Agent B (Running)
     │                                          │
     │ 1. Send message via                       │
     │    Communication Layer contract            │
     ▼                                          │
Communication Layer                              │
     │ 2. Route message                          │
     └───────────────────────────────────────────▶│
                                                  │ 3. Agent B receives message
                                                  │    within its own execution context
```

**Key rule:** an agent's execution context is never shared directly with another agent's. All coordination is mediated through message passing, ensuring that one agent's failure (Section 7) cannot directly corrupt another's state.

## 7. Error Handling

The Runtime follows the Fail Safe, Not Fail Silent principle established in `02-System-Architecture.md`, Section 8.4. Concretely:

| Error Category | Runtime Behavior |
|---|---|
| Tool invocation failure | Execution transitions to Failed unless the workflow graph explicitly defines a retry or fallback path |
| Unhandled exception within agent logic | Execution transitions to Failed; full checkpoint state and stack context are persisted for review |
| Approval rejection | Execution transitions to Failed; the rejection reason is persisted alongside the checkpoint |
| Scheduler resource exhaustion | New task submissions are rejected with an explicit capacity error; no task is silently dropped or queued indefinitely without visibility |
| State persistence failure | Execution is halted rather than allowed to proceed with unpersisted state, since an un-checkpointed execution cannot later be explained or resumed |

A Failed execution is always terminal and always inspectable — the Runtime never discards the state that led to a failure. This is what allows failures to be debugged after the fact rather than merely logged and forgotten.

## 8. Human Approval Checkpoints

The Runtime's Lifecycle Controller is the enforcement point for the human-oversight guarantee described in `05-Agent-OS.md`, Section 6:

1. Before executing any action, the Runtime checks whether the Approval Gateway classifies that action as important.
2. If important, the Lifecycle Controller transitions the execution to Awaiting Approval (Section 4.1) and halts further execution of that agent until a decision is recorded.
3. The Runtime does not proceed on an assumed or default decision under any circumstance — a missing decision keeps the execution in Awaiting Approval indefinitely, rather than timing out into an executed action.
4. Once a decision is recorded, the Lifecycle Controller applies the corresponding transition (Running on approval, Failed on rejection) exactly as defined in Section 4.1.

This means the Runtime structurally cannot execute a classified-important action without a recorded human decision — the guarantee does not depend on any Application remembering to request approval.

## 9. Extensibility

The Runtime is extensible along the following axes without requiring changes to its own internals:

| Extension Point | Mechanism |
|---|---|
| New workflow node types | Defined by the Workflow Engine and executed by the Runtime through the same generic execution-context interface |
| New scheduling policies | Implemented as an alternative Scheduler adapter behind the Runtime's internal scheduling interface (Section 3) |
| New execution backends (e.g., process vs. distributed worker) | Implemented as an alternative Execution Context Manager adapter |
| New persistence backends for checkpoints | Implemented behind the State Persistence Manager's interface, independent of the Memory System's own persistence (see `07-Memory-System.md`) |

Consistent with `02-System-Architecture.md`, Section 8.1 (Contracts Before Implementations), none of these extensions require Applications to change how they submit tasks or define workflows — the `runtime_contract` remains stable across any such internal evolution.

## 10. Relationship to Other Documents

This document defines the Runtime's internal architecture and execution semantics. It intentionally does not define:

- The conceptual meaning of lifecycle states → see `05-Agent-OS.md`, Section 4
- Memory data structures referenced by execution context → see `07-Memory-System.md`
- Tool invocation mechanics mediated during Waiting on Tool → see `08-Plugin-System.md`
- The public API surface through which Applications submit tasks → see `10-API-Standards.md`

Where a future document appears to describe a Runtime behavior inconsistent with the transition rules in Section 4.1, this document takes precedence until formally revised.