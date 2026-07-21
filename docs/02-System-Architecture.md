# Genesis — System Architecture

## 1. Purpose

This document defines the architecture of Genesis: its layers, the responsibilities of each component, the rules governing how components may depend on one another, and the mechanisms by which the system is intended to grow. It assumes the reader has already read `00-GENESIS_CONTEXT.md` and `01-Vision.md`, and it operationalizes the principles established there — most importantly, the Separation Principle (Core must never contain application-specific business logic).

This document describes architecture, not implementation. Where a decision is implementation-specific, it is deferred to the relevant subsystem document (`06-Agent-Runtime.md`, `07-Memory-System.md`, `08-Plugin-System.md`, `09-Database-Design.md`, `10-API-Standards.md`).

## 2. Design Goals

| Goal | Architectural Consequence |
|---|---|
| Application-agnostic Core | Core exposes only generic interfaces; no domain vocabulary lives in Core |
| Independent replaceability | Every subsystem is accessed through an interface/contract, never directly |
| Predictable execution | Agent execution follows a single, well-defined runtime model |
| Auditable autonomy | All state transitions and approval checkpoints are observable and logged |
| Incremental extensibility | Capability is added via plugins, not via modification of existing modules |
| Clear dependency direction | Dependencies flow in one direction only: Applications → Core → Infrastructure |

## 3. Architectural Style

Genesis follows a **layered, hexagonal-influenced architecture**. Core services expose ports (interfaces); infrastructure concerns (databases, message transports, external tool APIs) are implemented as adapters behind those ports. Applications consume Core exclusively through its public contracts and are never permitted to reach into Core internals or infrastructure directly.

This style was chosen because it directly enforces the Separation Principle: an architecture that only *encourages* separation will erode under deadline pressure, while one that structurally *requires* it does not.

## 4. High-Level System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                           Applications                           │
│                                                                    │
│   ┌───────────────────────┐        ┌───────────────────────┐     │
│   │  Product Manager v0.1 │        │  Future Application N  │     │
│   └───────────┬───────────┘        └───────────┬───────────┘     │
│               │                                │                 │
└───────────────┼────────────────────────────────┼─────────────────┘
                │        (Application Contracts / SDK)             │
┌───────────────▼────────────────────────────────▼─────────────────┐
│                        Genesis Core (Agent OS)                    │
│                                                                    │
│  ┌───────────┐ ┌───────────────┐ ┌───────────┐ ┌───────────────┐  │
│  │  Runtime  │ │ Workflow      │ │  Memory   │ │ Plugin System │  │
│  │           │ │ Engine        │ │  System   │ │               │  │
│  └─────┬─────┘ └───────┬───────┘ └─────┬─────┘ └───────┬───────┘  │
│        │               │               │               │         │
│  ┌─────▼─────┐   ┌─────▼──────┐  ┌─────▼─────┐  ┌───────▼──────┐  │
│  │Tool Manager│   │Communication│  │   Core     │  │  Approval    │  │
│  │            │   │   Layer     │  │ Services   │  │  Gateway     │  │
│  └─────┬──────┘   └─────┬──────┘  └─────┬─────┘  └───────┬──────┘  │
│        │                │               │                │         │
└────────┼────────────────┼───────────────┼────────────────┼─────────┘
         │                │               │                │
┌────────▼────────────────▼───────────────▼────────────────▼─────────┐
│                          Infrastructure Layer                       │
│   PostgreSQL   │   Message Transport   │   External Tool APIs      │
└───────────────────────────────────────────────────────────────────┘
```

## 5. Layer Responsibilities

### 5.1 Applications Layer

Owns all domain-specific logic, prompts, business rules, and user-facing behavior. An application is free to define its own agents, its own workflows, and its own data models — expressed entirely in terms of Genesis's public contracts.

**Responsible for:** domain intelligence, task-specific prompting, application data models, application-specific UI/API.
**Never responsible for:** execution scheduling, memory persistence mechanics, inter-agent transport, plugin loading.

### 5.2 Genesis Core (Agent Operating System)

The infrastructure layer that every application is built on. Composed of the following subsystems:

| Subsystem | Responsibility |
|---|---|
| Runtime | Executes agent tasks; owns the execution lifecycle (start, pause, resume, terminate) |
| Workflow Engine | Orchestrates multi-step and multi-agent workflows as declarative graphs |
| Memory System | Provides short-term (working) and long-term (persistent) memory abstractions |
| Plugin System | Loads, sandboxes, and exposes extensions/tools to the runtime |
| Tool Manager | Registers and mediates access to tools invoked by agents |
| Communication Layer | Handles message passing between agents, and between agents and humans |
| Core Services | Cross-cutting concerns: configuration, logging, authentication, authorization |
| Approval Gateway | Enforces human-approval checkpoints for actions classified as important (see `00-GENESIS_CONTEXT.md`, Section 9) |

Full subsystem-level detail for Runtime, Memory, and Plugin System is defined in `06-Agent-Runtime.md`, `07-Memory-System.md`, and `08-Plugin-System.md` respectively.

### 5.3 Infrastructure Layer

Concrete technology used to realize Core's ports: PostgreSQL for persistence, a message transport for asynchronous communication, and external tool APIs invoked through the Tool Manager. Infrastructure is always accessed through an adapter implementing a Core-defined interface — never referenced directly by Applications.

## 6. Dependency Rules

Genesis enforces dependency direction structurally, not by convention alone:

1. **Applications may depend on Core.** Core may never depend on any Application.
2. **Core may depend on Infrastructure interfaces (ports) it defines.** Core may never depend on a specific Infrastructure implementation (adapter) directly — only through the port.
3. **No subsystem within Core may depend on another subsystem's internal implementation.** Cross-subsystem interaction happens only through published interfaces (e.g., Workflow Engine calls Memory System only through the Memory System's public contract).
4. **Plugins may depend on the Tool Manager and Plugin System contracts.** Plugins may never depend on Runtime or Workflow Engine internals directly.
5. **Nothing depends on the Approval Gateway's internal decision logic** — only on its pass/fail contract. This ensures approval policy can change without destabilizing callers.

```
Applications
     │
     ▼
Genesis Core (public contracts only)
     │
     ▼
Infrastructure Ports  ──▶  Infrastructure Adapters
```

Any pull request introducing a dependency in the reverse direction is treated as an architectural defect (see `00-GENESIS_CONTEXT.md`, Section 13), not a style issue.

## 7. Component Interaction Model

A representative request flow — an application submitting a task to be executed by an agent — traverses the system as follows:

```
Application
   │  1. Submit task (via Application Contract / SDK)
   ▼
Runtime
   │  2. Instantiate execution context
   ▼
Workflow Engine
   │  3. Resolve task into a workflow graph
   ▼
Memory System            Tool Manager             Communication Layer
   │  4. Load/persist        │ 5. Invoke tools        │ 6. Coordinate with
   │     context              │    as required          │    other agents
   ▼                          ▼                         ▼
                    Approval Gateway
                       │  7. Gate any action classified as important
                       ▼
                    Human Reviewer
                       │  8. Approve / Reject
                       ▼
                    Runtime resumes execution
                       │  9. Return result
                       ▼
                    Application
```

Key properties of this flow:

- Steps 4–6 may occur zero or more times, in any order, depending on the workflow graph — they are not a fixed sequence.
- Step 7 is conditional: only actions classified as important trigger the Approval Gateway. Non-important actions proceed without a human checkpoint.
- Every step in this flow is logged through Core Services, making the entire execution path reconstructable after the fact (see Section 9, Observability).

## 8. Architectural Principles

### 8.1 Contracts Before Implementations

Every subsystem is designed contract-first. The interface a subsystem exposes is treated as a stable artifact; its implementation is treated as replaceable. This is what makes Section 6's replaceability guarantee enforceable rather than aspirational.

### 8.2 Explicit State, Not Hidden State

Agent execution state, memory contents, and workflow progress must be representable as inspectable data — not held only in ephemeral in-process state. This is a prerequisite for explainability (see `00-GENESIS_CONTEXT.md`, Section 8) and for the Runtime's pause/resume capability.

### 8.3 Composition Over Inheritance

Capability is added to the system by composing smaller units (plugins, tools, workflow nodes) rather than by subclassing or extending existing core classes. This keeps Core's surface area stable as the ecosystem of applications and plugins grows.

### 8.4 Fail Safe, Not Fail Silent

Whenever the Runtime, Workflow Engine, or Approval Gateway encounters an error or an ambiguous state, the default behavior is to halt and surface the condition for human review — never to guess and proceed silently.

## 9. Observability as an Architectural Concern

Observability is not treated as tooling bolted onto Core after the fact — it is a structural property of the architecture:

- Every subsystem emits state transitions through Core Services' logging interface using a common schema.
- Workflow Engine execution graphs are stored in a form that can be reconstructed and visualized after execution completes.
- Approval Gateway decisions (what was requested, who approved/rejected it, and why) are persisted independently of application data.

This ensures that explainability (Section 8, `00-GENESIS_CONTEXT.md`) is available uniformly across every application built on Genesis, without each application needing to implement its own logging or audit trail.

## 10. Future Extensibility

Genesis's architecture anticipates growth along several axes without requiring changes to the dependency rules in Section 6:

| Growth Axis | Extensibility Mechanism |
|---|---|
| New applications | Built entirely against existing Core contracts; no Core changes required |
| New tools/integrations | Registered through the Plugin System and Tool Manager; sandboxed from Core internals |
| New memory backends | Implemented as an adapter behind the Memory System's existing port |
| New workflow patterns | Expressed as new workflow graph definitions, not new Workflow Engine code paths |
| New communication transports | Implemented as an adapter behind the Communication Layer's existing port |
| Multi-tenant / multi-organization deployment | Addressed at the Core Services layer (authN/authZ, configuration) without touching Runtime or Workflow Engine |

Any extension that cannot be expressed through one of these mechanisms is a signal that the architecture itself may need to evolve — and any such evolution must be proposed as a revision to this document, not implemented informally.

## 11. Relationship to Other Documents

This document defines the structural architecture of Genesis. It intentionally does not specify:

- Concrete database schemas → see `09-Database-Design.md`
- API request/response contracts → see `10-API-Standards.md`
- Runtime execution semantics in detail → see `06-Agent-Runtime.md`
- Memory data structures and retrieval semantics → see `07-Memory-System.md`
- Plugin manifest format and sandboxing mechanics → see `08-Plugin-System.md`

Where any future document appears to conflict with the dependency rules or layer responsibilities defined here, this document takes precedence until formally revised.