# Genesis — Roadmap

## 1. Purpose

This document defines Genesis's phased evolution: what ships in each version, what capability each phase unlocks, and how later phases build on earlier ones without violating the architectural boundaries established in `02-System-Architecture.md` and the vision defined in `01-Vision.md`.

This roadmap describes sequencing and milestones. It does not redefine the target architecture itself — every phase below is a step toward the system already described in `00-GENESIS_CONTEXT.md` through `12-Development-Workflow.md`, not a deviation from it.

## 2. Roadmap Philosophy

### 2.1 Core Precedes Ecosystem

Genesis's roadmap is deliberately sequenced so that Core's contracts (`02-System-Architecture.md`, Section 8.1) stabilize before the ecosystem of Applications and third-party plugins is expected to grow. Building the AI Product Manager first (`00-GENESIS_CONTEXT.md`, Section 7) is not a detour from building Genesis — it is the mechanism by which Core's abstractions are validated under real load before other teams are asked to depend on them.

### 2.2 Every Phase Preserves the Separation Principle

No phase of this roadmap is permitted to ship a capability by embedding application-specific logic into Core (`00-GENESIS_CONTEXT.md`, Section 5). Where a milestone appears to require this, the milestone is redefined rather than the principle relaxed.

### 2.3 Versioning Reflects Contract Maturity

Version numbers below track the maturity and stability of Core's public contracts (`10-API-Standards.md`, Section 3), not calendar time or feature count. A version increments its major number only when Core's contracts reach a new stability guarantee.

## 3. Phase Overview

```
v0.1 (Beta)  ──▶  v0.2  ──▶  v0.3  ──▶  v1.0 (Stable Core)  ──▶  v1.x  ──▶  v2.0
Foundation        Hardening    Ecosystem     Stability            Scale      Multi-Tenant
                   & Approval   Enablement    Guarantee            & Growth   Platform
```

## 4. Phase 1 — Genesis Beta v0.1: Foundation

**Goal:** Validate that Genesis's core abstractions (Runtime, Memory, Workflow Engine, Plugin System) are sound by building the first reference application end-to-end.

**Milestones:**

| Milestone | Description |
|---|---|
| Core Runtime (baseline) | Execution lifecycle (`06-Agent-Runtime.md`, Section 4) implemented with in-process scheduling; pause/resume supported |
| Memory System (baseline) | Working memory and PostgreSQL-backed long-term memory (`07-Memory-System.md`, Sections 3–5), key-based and metadata retrieval only |
| Workflow Engine (baseline) | LangGraph-backed graph execution (`03-Tech-Stack.md`, Section 6.1) supporting linear and branching workflows |
| Plugin System (baseline) | Local plugin discovery and manifest validation (`08-Plugin-System.md`, Sections 5.1–5.2); no remote registry yet |
| Approval Gateway (baseline) | Manual approval-required action classification; single-reviewer approval flow (`05-Agent-OS.md`, Section 6) |
| AI Product Manager (v0.1) | First reference application generating PRDs, user stories, and market research, exercising the above subsystems end-to-end |
| Documentation set | `00`–`15` published and kept current with implementation (this document included) |

**Exit criteria:** The AI Product Manager can complete a full task lifecycle — submission, execution, tool use, approval, completion — using only Core's public contracts, with no Application-specific logic present in `core/`.

## 5. Phase 2 — v0.2: Hardening & Approval Maturity

**Goal:** Harden the guarantees introduced in v0.1 — particularly around failure handling, observability, and human oversight — before expanding surface area.

**Milestones:**

| Milestone | Description |
|---|---|
| Full lifecycle transition enforcement | Complete implementation and testing of the transition table in `06-Agent-Runtime.md`, Section 4.1, including invariant tests per `11-Coding-Standards.md`, Section 6.4 |
| Structured error handling | Full rollout of the error taxonomy in `10-API-Standards.md`, Section 5, across all Core endpoints |
| Observability baseline | Execution logs, checkpoints, and approval decisions uniformly queryable per `02-System-Architecture.md`, Section 9 |
| Multi-reviewer approval flows | Approval Gateway supports configurable reviewer requirements beyond a single reviewer (`05-Agent-OS.md`, Section 6) |
| Runtime scheduling improvements | Concurrency limits and fairness policies (`06-Agent-Runtime.md`, Section 5.1) made configurable per deployment |
| Expanded AI Product Manager coverage | Competitor analysis, functional/non-functional requirements, database design, and API specification generation added |

**Exit criteria:** Core's failure and approval paths are exercised in production with the AI Product Manager under realistic load, with no unhandled or silently-swallowed error paths remaining.

## 6. Phase 3 — v0.3: Ecosystem Enablement

**Goal:** Prepare Core's contracts for consumption by Applications and plugins the original team did not build, ahead of declaring contract stability in v1.0.

**Milestones:**

| Milestone | Description |
|---|---|
| Contract freeze candidate | `core/contracts/` reaches a proposed stable shape, reviewed explicitly against `10-API-Standards.md`, Section 3 |
| Remote plugin registry (initial) | First version of the versioned plugin registry described in `08-Plugin-System.md`, Section 8 |
| Plugin signing/provenance | Manifest schema extended to support the signing mechanism described in `08-Plugin-System.md`, Section 8, enabling safer third-party plugin adoption |
| Second Application (internal validation) | A second, distinct Application built against Core's contracts without any Core changes — the concrete test of the Separation Principle's success (`01-Vision.md`, Section 5) |
| Contract test suite maturity | Full contract-test coverage (`11-Coding-Standards.md`, Section 6.2) across every published Core contract |

**Exit criteria:** A second Application is built and operated using only documented Core contracts, with zero required changes to `core/`.

## 7. Phase 4 — v1.0: Stable Core

**Goal:** Declare Core's public contracts stable under the versioning guarantees in `10-API-Standards.md`, Section 3.2, and commit to backward compatibility going forward.

**Milestones:**

| Milestone | Description |
|---|---|
| Contract stability guarantee | `core/contracts/` (v1) frozen for additive-only evolution; breaking changes require a new major contract version thereafter |
| Production-grade deployment reference | Reference `infra/` configuration (`04-Folder-Structure.md`, Section 7) for production deployment, including Kubernetes manifests |
| Full observability & audit maturity | Every requirement in `02-System-Architecture.md`, Section 9, fully realized, including reconstructable execution history for compliance/audit use cases |
| Governance formalization | The review, architectural-review, and human-approval-gate processes in `12-Development-Workflow.md` fully codified with named maintainer roles |

**Exit criteria:** External teams can build and operate Applications on Genesis with a documented compatibility guarantee, without needing informal assurances from the original maintainers.

## 8. Phase 5 — v1.x: Scale & Growth

**Goal:** Scale Genesis's infrastructure to support significantly more concurrent executions, larger memory volumes, and a growing plugin ecosystem, without changing the contracts frozen in v1.0.

**Milestones:**

| Milestone | Description |
|---|---|
| Distributed Runtime execution | Execution Context Manager (`06-Agent-Runtime.md`, Section 3) gains a distributed-worker backend, behind the same Runtime contract |
| Long-term memory partitioning | `core_memory` partitioning by `application_id` (`09-Database-Design.md`, Section 7) implemented as volume warrants |
| Vector memory integration | The similarity-search retrieval mode anticipated in `07-Memory-System.md`, Section 8, implemented and exposed through the existing Memory System contract |
| Read replica topology | Read/write separation (`09-Database-Design.md`, Section 7) implemented for retrieval-heavy workloads |
| Plugin ecosystem growth tooling | Automated compatibility testing for third-party plugins (`08-Plugin-System.md`, Section 8) |

**Exit criteria:** Genesis demonstrably scales horizontally along each axis above without any consuming Application or plugin requiring a code change.

## 9. Phase 6 — v2.0: Multi-Tenant Platform

**Goal:** Support multiple independent organizations operating on a shared Genesis deployment, addressed — per the architectural boundary already established — at the Core Services layer rather than by altering Runtime, Workflow Engine, or Memory System internals (`02-System-Architecture.md`, Section 10).

**Milestones:**

| Milestone | Description |
|---|---|
| Multi-organization identity & authZ | Core Services (`02-System-Architecture.md`, Section 5.2) extended to support organization-scoped authentication and authorization |
| Tenant-level resource isolation | Runtime scheduling (`06-Agent-Runtime.md`, Section 5.1) and Memory System partitioning extended with an organization dimension alongside `application_id` |
| Tenant-scoped observability & billing hooks | Extension of the observability baseline (Section 5) to support per-tenant usage accounting |
| Marketplace-grade plugin ecosystem | Full realization of the plugin marketplace/directory concept described in `08-Plugin-System.md`, Section 8, as an Application built on Core, not a Core feature |

**Exit criteria:** Multiple organizations operate independent Applications on a single shared Genesis deployment with enforced data and resource isolation, without any change to the v1.0 contract guarantees.

## 10. Long-Term Evolution

Beyond v2.0, Genesis's evolution is expected to be driven by the ecosystem of Applications and plugins built on it, rather than by a small planning group anticipating every future need — consistent with the Extensibility Over Anticipation principle (`01-Vision.md`, Section 4.4). This roadmap will be revised at each phase boundary to reflect what the ecosystem has actually demanded, rather than treated as a fixed prediction made once at project inception.

## 11. Relationship to Other Documents

This document defines sequencing and milestones. It intentionally does not redefine:

- The target architecture each phase builds toward → see `02-System-Architecture.md`
- The contract stability guarantees referenced in Phase 4 → see `10-API-Standards.md`, Section 3
- The review process that gates each milestone's completion → see `12-Development-Workflow.md`

Where a milestone above appears to require relaxing a principle in `00-GENESIS_CONTEXT.md` or `02-System-Architecture.md`, the milestone is reconsidered — this roadmap is subordinate to those documents, not the reverse.