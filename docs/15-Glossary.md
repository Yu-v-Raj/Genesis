# Genesis — Glossary

## 1. Purpose

This document defines every architectural, technical, and project-specific term used across the Genesis documentation set (`00`–`14`). Terms are listed alphabetically. Each entry references the document where the concept is defined in full detail; this glossary provides a concise, authoritative definition, not a substitute for that source.

## 2. Terms

**Agent**
A unit of autonomous execution run by the Agent OS, defined by an Application through an Agent Specification. See `14-Agent-Specifications.md`.

**Agent Operating System (Agent OS)**
The infrastructure layer of Genesis — Runtime, Workflow Engine, Memory System, Plugin System, Tool Manager, Communication Layer, Core Services, and Approval Gateway — that executes agents without knowledge of any application's domain logic. See `05-Agent-OS.md`.

**Agent Specification**
The standard manifest format every agent must conform to, declaring its identity, responsibilities, interfaces, permissions, and memory access. See `14-Agent-Specifications.md`.

**Application**
Software built on top of Genesis Core that provides domain intelligence (e.g., the AI Product Manager). Applications depend on Core; Core never depends on Applications. See `02-System-Architecture.md`, Section 5.1.

**Application Contract**
The published interface (API and SDK surface) through which an Application interacts with Genesis Core. See `02-System-Architecture.md`, Section 6.

**Approval Gateway**
The Core subsystem that enforces human-approval checkpoints for actions classified as important, halting execution until a decision is recorded. See `05-Agent-OS.md`, Section 6; `06-Agent-Runtime.md`, Section 8.

**Architectural Review**
The mandatory review step, distinct from standard code review, that verifies a Core change or new subsystem complies with Genesis's dependency rules and separation principles. See `12-Development-Workflow.md`, Section 8.

**Awaiting Approval**
The agent lifecycle state entered when an execution attempts an action classified as important, pending a human decision. See `05-Agent-OS.md`, Section 4; `06-Agent-Runtime.md`, Section 4.1.

**Checkpoint**
A persisted snapshot of an execution's workflow position, memory reference, and triggering event, written at every lifecycle-state transition. See `06-Agent-Runtime.md`, Section 4.2.

**Communication Layer**
The Core subsystem handling message passing between agents, and between agents and humans. See `02-System-Architecture.md`, Section 5.2; `06-Agent-Runtime.md`, Section 6.

**Contract-First (Contracts Before Implementations)**
The architectural principle that every subsystem's interface is designed and stabilized before its implementation, treating the interface as the stable artifact and the implementation as replaceable. See `02-System-Architecture.md`, Section 8.1.

**Core (Genesis Core)**
The Agent Operating System layer of Genesis, containing no application-specific business logic. See `00-GENESIS_CONTEXT.md`, Section 5.

**Core Services**
The Core subsystem providing cross-cutting concerns: configuration, logging, authentication, and authorization. See `02-System-Architecture.md`, Section 5.2.

**Data Source (Plugin Capability Type)**
A plugin capability type providing read-only access to external data for the Memory System or an agent. See `08-Plugin-System.md`, Section 3.3.

**Dependency Rules**
The set of enforced constraints governing which layers and subsystems may depend on which others (Applications → Core → Infrastructure, never the reverse). See `02-System-Architecture.md`, Section 6.

**Design Proposal**
The written document required before implementing a Core change, describing affected subsystems, architectural compliance, and test strategy. See `12-Development-Workflow.md`, Section 3.2.

**Entity Boundary**
The rule that a database table belongs to exactly one subsystem or Application owner, mirroring architectural ownership at the schema level. See `09-Database-Design.md`, Section 4.

**Execution Context**
The isolated environment (memory handles, tool access, identity) constructed by the Runtime for a single agent execution. See `06-Agent-Runtime.md`, Section 3.

**Execution Context Manager**
The Runtime component responsible for constructing and tearing down execution contexts. See `06-Agent-Runtime.md`, Section 3.

**Explicit State**
The architectural principle that agent execution state, memory contents, and workflow progress must be represented as inspectable data, never held only in ephemeral in-process state. See `02-System-Architecture.md`, Section 8.2.

**Fail Safe, Not Fail Silent**
The principle that ambiguous states or errors cause execution to halt and surface for human review rather than proceed on a silent guess. See `02-System-Architecture.md`, Section 8.4.

**Genesis**
The extensible Agent Operating System providing a unified runtime, memory, orchestration, and plugin architecture for autonomous AI applications. See `00-GENESIS_CONTEXT.md`.

**Human-Approval Gate**
The additional, explicit maintainer approval required before a Core change is merged, distinct from standard reviewer approval. See `12-Development-Workflow.md`, Section 9.

**Important Action**
An action classified as irreversible, externally visible, or high-impact, requiring a human-approval checkpoint before execution proceeds. See `00-GENESIS_CONTEXT.md`, Section 9; `05-Agent-OS.md`, Section 6.

**Least Privilege by Default**
The security posture under which a newly discovered plugin (or agent, per its declared permissions) has no capability beyond what it explicitly declares and has validated. See `08-Plugin-System.md`, Section 6.2.

**Lifecycle Controller**
The Runtime component enforcing valid agent lifecycle-state transitions and routing to the Approval Gateway or Tool Manager as required. See `06-Agent-Runtime.md`, Section 3.

**Long-Term Memory**
The Memory System layer holding records intended to persist beyond a single execution, backed by PostgreSQL. See `07-Memory-System.md`, Section 3.2.

**Memory Backend (Plugin Capability Type)**
A plugin capability type implementing an alternative persistence adapter behind the Memory System's port. See `08-Plugin-System.md`, Section 3.3.

**Memory System**
The Core subsystem providing working and long-term memory abstractions to agents, without knowledge of what is being stored. See `07-Memory-System.md`.

**Monorepo**
The single-repository model housing Genesis Core, all Applications, shared packages, infrastructure code, and documentation. See `04-Folder-Structure.md`, Section 2.

**Plugin**
A self-contained, manifest-declared package extending Genesis with a new tool, data source, communication adapter, or memory backend, without modifying Core. See `08-Plugin-System.md`.

**Plugin System**
The Core subsystem responsible for discovering, validating, registering, and sandboxing plugins. See `08-Plugin-System.md`.

**Product Manager (AI Product Manager)**
The first reference Application built on Genesis, generating PRDs, user stories, market research, and related product artifacts to validate Genesis's abstractions. See `00-GENESIS_CONTEXT.md`, Section 7.

**Quarantined**
The plugin lifecycle state entered automatically when an Active plugin attempts an action outside its declared, validated permissions. See `08-Plugin-System.md`, Section 6.3.

**Replaceability**
The design goal that any Core subsystem's implementation can be swapped for an alternative without destabilizing the rest of the system, provided the replacement honors the existing contract. See `00-GENESIS_CONTEXT.md`, Section 10.

**Runtime**
The Core subsystem responsible for executing agents according to their defined lifecycle: scheduling, execution context management, state persistence, and lifecycle control. See `06-Agent-Runtime.md`.

**Scheduler**
The Runtime component deciding when and in what order pending agent executions are admitted to run, subject to concurrency and fairness constraints. See `06-Agent-Runtime.md`, Section 5.1.

**Separation Principle**
The invariant that Genesis Core must never contain application-specific business logic. See `00-GENESIS_CONTEXT.md`, Section 5.

**Sandboxing**
The runtime enforcement mechanism ensuring a plugin can only access the network hosts, filesystem paths, or tool APIs it has explicitly declared and had validated. See `08-Plugin-System.md`, Section 6.1.

**State Persistence Manager**
The Runtime component responsible for persisting lifecycle checkpoints so execution can be paused, resumed, or recovered after failure. See `06-Agent-Runtime.md`, Section 3.

**Tool**
An action an agent can invoke through the Tool Manager, typically calling an external API or service, registered via the Plugin System. See `08-Plugin-System.md`, Section 3.3.

**Tool Manager**
The Core subsystem that registers tools and mediates their invocation by agents. See `02-System-Architecture.md`, Section 5.2.

**Working Memory**
The Memory System layer scoped to a single agent execution, holding current task input, intermediate artifacts, and tool results. See `07-Memory-System.md`, Section 3.1.

**Workflow Engine**
The Core subsystem orchestrating multi-step and multi-agent workflows as declarative graphs. See `02-System-Architecture.md`, Section 5.2.

**Workflow Graph**
A declarative representation of the steps an agent or set of agents takes to complete a task, defined by an Application and executed by the Runtime. See `02-System-Architecture.md`, Section 7.

## 3. Relationship to Other Documents

This glossary is a summary reference, not a source of architectural authority. Where a definition here appears to conflict with its source document, the source document — cross-referenced in each entry — takes precedence. As new terms are introduced by future revisions to `00`–`14`, this glossary is updated in the same change, per the documentation-consistency requirement in `12-Development-Workflow.md`, Section 10.1.