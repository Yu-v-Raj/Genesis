# Genesis — Agent Operating System

## 1. Purpose

This document defines the Agent Operating System (Agent OS) at the conceptual level: its philosophy, its responsibilities, the lifecycle it governs, its boundaries, and the capabilities it exposes to Applications. It sits between `02-System-Architecture.md` (which defines the layered structure of Genesis) and the subsystem-specific documents (`06-Agent-Runtime.md`, `07-Memory-System.md`, `08-Plugin-System.md`), which define implementation-level detail for each of the Agent OS's parts.

Everything in this document must remain true regardless of which application runs on top of Genesis. If a statement here can only be justified by referring to the Product Manager application, it does not belong in this document.

## 2. Philosophy

### 2.1 An Operating System for Agents, Not a Framework for One Agent

The term "Agent Operating System" is deliberate, not decorative. A framework typically helps a developer build *one* kind of thing well. An operating system provides the primitives — process management, memory, I/O, scheduling — that let arbitrarily many, unanticipated programs run safely on shared infrastructure.

Genesis's Agent OS adopts the same posture toward agents: it does not assume what an agent is *for*. It assumes only that an agent is a unit of autonomous execution that needs to be run, given memory, given tools, coordinated with other agents, and — when its actions matter enough — checked by a human before proceeding.

### 2.2 Autonomy Is Bounded by Design, Not by Convention

The Agent OS treats bounded autonomy as a structural property, not a best practice that individual applications are trusted to implement correctly. Every capability the Agent OS exposes — execution, memory, tool access, inter-agent communication — is mediated through the OS itself, which means the boundaries on agent behavior (approval checkpoints, resource limits, observability) apply uniformly, regardless of which application or which agent is running.

### 2.3 The Agent OS Has No Opinion About Task Content

The Agent OS knows how to execute a workflow graph, persist memory, invoke a registered tool, and route a message. It has no concept of a "PRD," a "sprint," or a "competitor" — those are meaningful only within the Product Manager application. This is the Separation Principle (`00-GENESIS_CONTEXT.md`, Section 5) restated at the level of the Agent OS's own self-understanding: if the Agent OS ever needs to know what a task *means* in order to execute it, that is an architectural failure, not a missing feature.

## 3. Responsibilities

The Agent OS is responsible for the following, and only the following:

| Responsibility | Description |
|---|---|
| Execution | Running agent tasks according to a defined lifecycle (Section 4), regardless of what the task represents |
| Memory | Providing working and persistent memory abstractions that any agent can use, without knowing the shape of the data being stored |
| Coordination | Enabling multiple agents to communicate and coordinate through a common protocol |
| Tool Mediation | Exposing tools to agents through a uniform invocation interface, regardless of what the tool does |
| Extensibility | Allowing new tools, agents, and capabilities to be added via the Plugin System without modifying the OS itself |
| Human Oversight | Enforcing approval checkpoints for actions classified as important, independent of which application defined the action |
| Observability | Making agent execution, memory access, and coordination events inspectable after the fact |

The Agent OS is explicitly **not** responsible for: deciding what a "good" output looks like for any task, defining domain-specific prompts, or making judgment calls about task content. Those responsibilities belong entirely to Applications (see `02-System-Architecture.md`, Section 5.1).

## 4. Agent Lifecycle

Every agent execution managed by the Agent OS passes through the same lifecycle, regardless of the application that initiated it:

```
        ┌───────────┐
        │  Created   │   Agent instantiated with a task and execution context
        └─────┬─────┘
              ▼
        ┌───────────┐
        │  Running   │   Agent actively executing within a workflow graph
        └─────┬─────┘
              │
     ┌────────┼─────────────┐
     ▼        ▼              ▼
┌─────────┐ ┌────────┐  ┌───────────┐
│ Paused   │ │ Waiting │  │ Awaiting  │
│(resumable)│ │on Tool  │  │ Approval  │
└────┬────┘ └────┬───┘  └─────┬─────┘
     │            │             │
     └──────┬─────┴─────────────┘
            ▼
       ┌───────────┐
       │  Running   │  (resumes)
       └─────┬─────┘
             ▼
     ┌───────┴────────┐
     ▼                ▼
┌──────────┐     ┌───────────┐
│ Completed │     │  Failed    │
└──────────┘     └───────────┘
```

**Lifecycle states, defined:**

| State | Meaning |
|---|---|
| Created | The Agent OS has instantiated an execution context for a task but has not yet begun executing it |
| Running | The agent is actively executing steps within its assigned workflow graph |
| Paused | Execution has been explicitly suspended and its state persisted; it can be resumed later, potentially after the process restarts |
| Waiting on Tool | Execution is blocked pending the result of a tool invocation mediated by the Tool Manager |
| Awaiting Approval | Execution is blocked pending a human decision at the Approval Gateway (see Section 6) |
| Completed | The agent's task finished successfully; its final state and outputs are persisted |
| Failed | Execution halted due to an unrecoverable error; the failure state and diagnostic context are persisted for review |

This lifecycle is deliberately identical across all applications. An application may define what happens *within* the Running state (which workflow graph, which agents), but it may not introduce new lifecycle states or bypass any of the states above.

## 5. Boundaries

### 5.1 What the Agent OS Will Never Do

- It will never execute an action classified as important without a corresponding Approval Gateway checkpoint having passed.
- It will never persist agent memory or execution state in a form that cannot later be inspected or reconstructed (see `02-System-Architecture.md`, Section 8.2, Explicit State).
- It will never allow an agent to invoke a tool that has not been registered and mediated through the Tool Manager.
- It will never embed knowledge of a specific application's domain vocabulary into its own decision logic.

### 5.2 What Applications Must Never Assume

- Applications must never assume they can bypass the Agent OS's lifecycle or Approval Gateway by calling infrastructure (e.g., the database, a message transport) directly. All such access is mediated (`02-System-Architecture.md`, Section 6).
- Applications must never assume a specific Agent OS subsystem implementation (e.g., a specific memory backend) — only the contract that subsystem publishes (`02-System-Architecture.md`, Section 8.1).

## 6. Human Oversight as an Agent OS Capability

Human oversight is implemented as a first-class capability of the Agent OS, not a feature of any individual application. The Agent OS classifies actions as **important** or **routine** based on criteria defined at the OS level (irreversibility, external visibility, impact) — not based on any application's internal notion of what matters. When an action is classified as important, the Agent OS transitions the executing agent into the Awaiting Approval lifecycle state (Section 4) and routes the decision to a human reviewer through the Approval Gateway. Execution resumes only once a decision has been recorded.

This ensures that no application, by omission or oversight, can ship an agent capable of taking a consequential action without a human checkpoint — the guarantee is enforced by the OS, not requested of the application.

## 7. Capabilities Exposed to Applications

The Agent OS exposes its responsibilities to Applications through the contracts defined in `core/contracts/` (see `04-Folder-Structure.md`, Section 4). At the conceptual level, these capabilities are:

| Capability | What an Application Can Do With It |
|---|---|
| Task submission | Submit a unit of work to be executed as an agent, without specifying how execution is scheduled |
| Workflow definition | Define a workflow graph describing the steps an agent should take, using Agent-OS-defined node types |
| Memory access | Read and write working/persistent memory without needing to know its storage implementation |
| Tool registration | Register domain-specific tools through the Plugin System, to be invoked by agents via the Tool Manager |
| Agent-to-agent messaging | Send and receive messages between agents through the Communication Layer's protocol |
| Execution inspection | Query the current lifecycle state, history, and logs of any agent execution it owns |

Applications are given no capability that would allow them to circumvent the lifecycle (Section 4), the approval requirement (Section 6), or the dependency rules established in `02-System-Architecture.md`.

## 8. Relationship to Other Documents

This document defines the Agent OS conceptually — its philosophy, responsibilities, lifecycle, and boundaries. It intentionally does not define:

- The concrete execution model and scheduling mechanics → see `06-Agent-Runtime.md`
- Memory data structures and retrieval semantics → see `07-Memory-System.md`
- Plugin manifest format, sandboxing, and registration mechanics → see `08-Plugin-System.md`
- API-level request/response shapes for these capabilities → see `10-API-Standards.md`

Where a future subsystem document appears to grant a capability inconsistent with the boundaries defined in Section 5, this document takes precedence until formally revised.