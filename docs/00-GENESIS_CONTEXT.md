# Genesis — Project Context

## 1. Purpose of This Document

This document is the canonical entry point for anyone contributing to, evaluating, or building on top of Genesis. It exists to prevent architectural drift by stating, in one place, what Genesis *is*, what it is *not*, and the non-negotiable boundaries that every subsequent design decision must respect.

Every other document in this documentation set assumes the reader has read this one first.

## 2. What Genesis Is

Genesis is an extensible **Agent Operating System**. It provides a unified runtime, memory system, orchestration engine, and plugin architecture on top of which autonomous AI applications are built and executed.

Genesis occupies the same conceptual layer in an AI-native stack that a traditional operating system occupies in a classical compute stack: it does not know or care what any particular application does, but it guarantees the primitives every application needs in order to run safely, predictably, and at scale.

## 3. What Genesis Is Not

| Genesis Is | Genesis Is Not |
|---|---|
| Infrastructure for running agents | An AI application itself |
| A runtime, memory, and orchestration layer | A chatbot, PRD generator, or vertical tool |
| Application-agnostic by design | Coupled to any single use case |
| A platform other teams build on | A monolith that grows business logic over time |

This distinction is architectural law, not a stylistic preference. See Section 5.

## 4. Core Vision Statement

> Genesis is an extensible Agent Operating System that provides a unified runtime, memory, orchestration, and plugin architecture for autonomous AI applications.

Applications run **on** Genesis. Genesis provides infrastructure. Applications provide intelligence.

## 5. The Separation Principle

**Genesis Core must never contain application-specific business logic.**

This is the single most important invariant in the entire project. It governs every design review, every pull request, and every future roadmap decision. Concretely:

- Core services (runtime, workflow engine, memory, plugin system, tool manager, communication layer) must be usable by an application Genesis's maintainers have never heard of.
- Any logic that only makes sense in the context of one specific application belongs in an **Application**, not in **Core**.
- If a feature request cannot be justified without naming a specific application, it does not belong in Core.
- Violations of this principle are treated as architectural defects, regardless of short-term convenience.

## 6. System Composition

Genesis is composed of a Core layer (Runtime, Workflow Engine, Memory System, Plugin System, Tool Manager, Communication Layer, Core Services) and an Applications layer (Product Manager v0.1, Future Applications). Core and Applications are developed, versioned, and reasoned about as distinct concerns. An Application depends on Core; Core never depends on an Application.

## 7. First Reference Application: AI Product Manager

The first application built on top of Genesis is an **AI Product Manager**, existing purely to exercise Genesis's runtime, memory, orchestration, and plugin systems under a realistic workload. It generates PRDs, user stories, market research, competitor analysis, functional and non-functional requirements, database design, API specifications, sprint planning, software architecture, and technical documentation.

If building this application ever requires Genesis Core to know what a "PRD" or a "sprint" is, that signals the abstraction boundary was drawn incorrectly — not that Core should be extended to accommodate it.

## 8. Guiding Engineering Principles

| Principle | Meaning |
|---|---|
| Modular | Every subsystem is a discrete, independently understandable unit |
| Extensible | New capabilities are added via plugins/extensions, not core modification |
| Scalable | The system grows from a single agent to many concurrent agents/workflows |
| Explainable | Agent decisions and workflow state are inspectable, not opaque |
| Human-Centered | Humans remain the final authority over consequential actions |
| Production-Ready | Designs favor operational correctness over prototype convenience |

## 9. Human Authority Over Important Actions

Any action classified as important — irreversible, externally visible, or high-impact — must pass through an explicit human-approval checkpoint before execution, enforced at the runtime/workflow level so no application can bypass it by omission.

## 10. Replaceability

Every module in Genesis Core is independently replaceable. A team must be able to swap the Memory System, Workflow Engine, or Plugin System's implementation without rewriting other subsystems, provided the replacement honors the existing contract.

## 11. Technology Stack Summary

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, TailwindCSS |
| Backend | FastAPI, Python |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Agent Framework | LangGraph |
| Authentication | JWT |
| Version Control | Git, GitHub |

## 12. Non-Negotiable Invariants (Summary)

1. Genesis Core never contains application-specific business logic.
2. Applications depend on Core; Core never depends on Applications.
3. Important/irreversible actions require explicit human approval.
4. Every Core module must be independently replaceable.
5. New capability is added through extension (plugins), not modification of Core internals.