# Genesis — Agent Specifications

## 1. Purpose

This document defines the standard specification every agent running on Genesis must conform to, regardless of which Application defines it. Where `05-Agent-OS.md` defines the Agent OS's own philosophy and lifecycle, and `06-Agent-Runtime.md` defines how that lifecycle is executed, this document defines the shape an Application must give an individual agent so that the Runtime, Memory System, Plugin System, and Approval Gateway can all interoperate with it uniformly.

This document defines a specification format, not any specific agent's behavior. The Product Manager application's agents (e.g., a PRD-drafting agent, a market-research agent) are conforming *instances* of this specification, referenced here only as illustrative examples — never as requirements this specification itself depends on.

## 2. Why a Standard Specification Is Required

Per the Separation Principle (`00-GENESIS_CONTEXT.md`, Section 5), Genesis Core has no knowledge of what any agent does. This is only possible because every agent, regardless of Application, presents itself to Core in the same structural shape. The Agent Specification is that shape: it is what allows the Runtime to schedule an agent (`06-Agent-Runtime.md`), the Memory System to scope its context (`07-Memory-System.md`), the Plugin System to mediate its tool access (`08-Plugin-System.md`), and the Approval Gateway to classify its actions (`05-Agent-OS.md`, Section 6) — all without any of those subsystems knowing what the agent is *for*.

## 3. Specification Structure

Every agent is defined by a manifest with the following required sections:

```
agent:
  identity:
    name: string
    version: semver
    application_id: string        # owning Application, see 04-Folder-Structure.md, Section 5

  responsibilities:
    description: string           # human-readable purpose, application-defined
    inputs: [schema_ref]          # expected input contract(s)
    outputs: [schema_ref]         # expected output contract(s)

  lifecycle_bindings:
    workflow_graph_ref: string    # the workflow graph this agent executes within, see 06-Agent-Runtime.md

  interfaces:
    invocation_contract: schema_ref
    communication_contract: schema_ref

  permissions:
    tools: [tool_id]
    memory_scopes: [scope]
    approval_required_actions: [action_id]

  memory_access:
    working_memory: read_write
    long_term_memory:
      read: [key_pattern]
      write: [key_pattern]

  extensibility:
    plugin_dependencies: [plugin_id]
```

Each section below defines the requirements for one part of this manifest.

## 4. Identity

| Field | Requirement |
|---|---|
| `name` | Unique within the owning Application; follows `snake_case` per `04-Folder-Structure.md`, Section 9 |
| `version` | Semantic version, incremented per the same discipline as Core contracts (`10-API-Standards.md`, Section 3) |
| `application_id` | Must match a registered Application (`04-Folder-Structure.md`, Section 5); an agent cannot exist without an owning Application |

An agent's identity is immutable once Registered with the Plugin System's agent-registration extension of Section 3.3's capability types (`08-Plugin-System.md`) — a new version is a new manifest entry, not a mutation of an existing one, preserving the auditability requirement in `02-System-Architecture.md`, Section 9.

## 5. Responsibilities

The `responsibilities` section is entirely Application-defined content, opaque to Core — the Agent OS never inspects `description` for meaning. What Core *does* enforce is that `inputs` and `outputs` are declared as schema references conforming to `10-API-Standards.md`'s explicit-typing conventions (Section 2.3), so that:

- The Workflow Engine can validate that an agent's declared inputs match what its position in the workflow graph will actually provide.
- The Memory System can validate that promoted long-term memory records (`07-Memory-System.md`, Section 4.3) match an agent's declared output shape, if the Application chooses to enforce this.

An agent whose declared inputs/outputs do not conform to a valid schema reference fails validation at registration time (Section 8), the same way a Plugin manifest fails validation for policy violations (`08-Plugin-System.md`, Section 5.2).

## 6. Lifecycle Bindings

Every agent specification references exactly one workflow graph it executes within (`workflow_graph_ref`). The agent itself does not define its own lifecycle — it inherits the lifecycle states and transition rules from `06-Agent-Runtime.md`, Section 4.1, exactly as any other execution does. This section exists only to bind the agent's identity to a specific workflow graph definition (`core_workflow`, per `09-Database-Design.md`, Section 3.1) — it does not introduce agent-specific lifecycle states.

## 7. Interfaces

### 7.1 Invocation Contract

The `invocation_contract` defines how the Runtime instantiates this agent's execution context (`06-Agent-Runtime.md`, Section 3) — what parameters are required to create an Execution Context for this specific agent, expressed as a schema reference, never as untyped keyword arguments.

### 7.2 Communication Contract

The `communication_contract` defines what message shapes this agent can send and receive through the Communication Layer (`06-Agent-Runtime.md`, Section 6). An agent that has not declared a communication contract cannot participate in inter-agent messaging — the Communication Layer rejects undeclared message types at routing time, consistent with the Explicit Over Implicit principle (`10-API-Standards.md`, Section 2.3).

## 8. Permissions

### 8.1 Tool Permissions

The `permissions.tools` list declares which registered tools (`08-Plugin-System.md`, Section 3.3) this agent may invoke through the Tool Manager. This mirrors, at the agent level, the same least-privilege-by-default posture the Plugin System enforces for plugins (`08-Plugin-System.md`, Section 6.2): an agent has no tool access beyond what it explicitly declares, and the Tool Manager rejects any invocation attempt outside this list.

### 8.2 Memory Scope Permissions

The `permissions.memory_scopes` list declares which long-term memory `key` patterns (`07-Memory-System.md`, Section 5) this agent may read or write, in addition to the read/write rules in Section 9 below. This prevents an agent from reading or writing memory records outside its Application's intended scope even within its own `application_id` boundary (`07-Memory-System.md`, Section 6).

### 8.3 Approval-Required Actions

The `permissions.approval_required_actions` list declares which of this agent's actions the owning Application considers important, feeding into the Approval Gateway's classification (`05-Agent-OS.md`, Section 6). This declaration does not itself grant or bypass approval — the Approval Gateway independently enforces that any listed action transitions the execution to Awaiting Approval (`06-Agent-Runtime.md`, Section 4.1) regardless of what the agent's own code attempts to do.

## 9. Memory Access

### 9.1 Working Memory

Every agent has read/write access to its own working memory (`07-Memory-System.md`, Section 3.1), scoped strictly to its own execution — this is granted implicitly by the Runtime's Execution Context Manager (`06-Agent-Runtime.md`, Section 3) and is not separately declared in the manifest.

### 9.2 Long-Term Memory

The `memory_access.long_term_memory` section declares, via `key_pattern` entries, exactly which long-term memory keys this agent may read and which it may write, consistent with the promotion rules in `07-Memory-System.md`, Section 4.3. An agent attempting to read or write a key outside its declared patterns is rejected by the Memory System at the contract boundary, not merely discouraged by convention.

## 10. Extensibility

### 10.1 Plugin Dependencies

The `extensibility.plugin_dependencies` list declares which plugins (`08-Plugin-System.md`, Section 5.3) this agent's tool and memory-backend permissions (Section 8) depend on. This mirrors plugin-to-plugin dependency declarations and is resolved the same way at registration time — an agent cannot be Registered if a declared plugin dependency is not itself Registered and Active.

### 10.2 Adding New Agent Capability Without Changing This Specification

Because this specification is deliberately generic — declaring inputs/outputs, permissions, and memory scopes as data rather than code — new agent behavior is added entirely by:

- Defining a new manifest instance (Sections 3–9) within an Application.
- Registering new tools/plugins it depends on (`08-Plugin-System.md`).
- Defining or extending a workflow graph it binds to (Section 6).

None of these require a change to this specification format or to any Core subsystem, which is the direct, agent-level realization of the Extensibility Over Anticipation principle (`01-Vision.md`, Section 4.4).

## 11. Registration and Validation

An agent specification is validated before it can be bound to a workflow graph and executed, following the same discipline as Plugin validation (`08-Plugin-System.md`, Section 5.2):

1. **Manifest well-formedness** — all required sections (Section 3) are present and schema-valid.
2. **Permission declarations resolve** — declared tools, memory scopes, and plugin dependencies (Section 8, Section 10.1) exist and are Active.
3. **Interface contracts are valid schema references** — invocation and communication contracts (Section 7) parse against `10-API-Standards.md`'s schema conventions.

An agent specification failing any of these checks is not Registered, and cannot be bound to a workflow graph execution.

## 12. Relationship to Other Documents

This document defines the standard shape every agent specification must take. It intentionally does not define:

- The lifecycle states an agent's execution passes through once Registered → see `06-Agent-Runtime.md`, Section 4
- How declared tool permissions are mediated at invocation time → see `08-Plugin-System.md`
- How declared memory scopes are persisted and queried → see `07-Memory-System.md`
- The API endpoints used to submit or query an agent's execution → see `10-API-Standards.md`

Where a specific Application's agent definitions appear to require a manifest field not covered by Sections 3–10, that gap is raised as a proposed revision to this document, not addressed by an ad hoc, undocumented extension within a single Application.