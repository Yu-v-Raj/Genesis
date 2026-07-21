# Genesis — Tech Stack

## 1. Purpose

This document records the concrete technology choices made for Genesis, the role each technology plays, the alternatives considered, the trade-offs accepted, and how each choice scales as the system grows. It assumes the reader has read `00-GENESIS_CONTEXT.md` and `02-System-Architecture.md`.

Per the Separation Principle and the dependency rules in `02-System-Architecture.md`, every technology listed here is bound to Core through an interface (port), not referenced directly by Applications. This document justifies *what* was chosen; it does not redefine *how* it is wired into the architecture — see `02-System-Architecture.md`, Section 6, for that.

## 2. Summary Table

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

## 3. Frontend

### 3.1 Next.js

**Role:** Application framework for all Genesis-adjacent web UIs, including the Product Manager reference application's dashboard.

**Why chosen:**
- File-system-based routing and built-in server-side rendering reduce boilerplate for dashboard-style applications with authenticated, data-heavy views.
- First-class support for API routes allows lightweight backend-for-frontend endpoints without introducing a second backend framework for UI-specific concerns.
- Strong alignment with the React ecosystem, minimizing the number of frontend paradigms contributors must learn.

**Alternatives considered:**
| Alternative | Reason Not Chosen |
|---|---|
| Plain React (Vite/CRA) | Would require manually assembling routing, SSR, and build tooling that Next.js provides out of the box |
| Remix | Comparable capability, but smaller ecosystem and hiring pool at project inception |
| SvelteKit | Excellent DX, but breaks alignment with React, which the rest of the stack and contributor base is built around |

**Trade-offs accepted:** Next.js's opinionated structure and frequent framework-level changes introduce some upgrade overhead over time; this is accepted in exchange for reduced initial tooling burden.

**Scalability outlook:** Next.js scales well from a single dashboard to many application-specific frontends, since each Application can ship its own Next.js frontend consuming Genesis Core through the same public API contracts (see `10-API-Standards.md`).

### 3.2 React

**Role:** Component model underlying all Genesis frontends.

**Why chosen:** Ubiquity, mature ecosystem, and direct compatibility with Next.js. React's component model maps cleanly onto the kind of composable, inspectable UI that dashboards for agent execution state require.

**Alternatives considered:** Vue, Svelte — both viable, but rejected to avoid fragmenting frontend expertise across the project and its future contributors.

**Trade-offs accepted:** React's flexibility means UI consistency depends on discipline (component libraries, design tokens) rather than framework enforcement.

### 3.3 TypeScript

**Role:** Primary language for all frontend code.

**Why chosen:** Static typing catches an entire class of integration errors between frontend and Core's API contracts before runtime, which matters disproportionately for a system whose backend models (agent state, workflow graphs, memory records) are inherently complex and evolving.

**Alternatives considered:** Plain JavaScript — rejected because the cost of type errors in a system this structurally complex outweighs the reduced upfront friction of an untyped language.

**Scalability outlook:** As Genesis's API surface grows, TypeScript types generated from Core's API schema (see `10-API-Standards.md`) keep frontend and backend contracts synchronized automatically.

### 3.4 TailwindCSS

**Role:** Styling methodology for all frontend surfaces.

**Why chosen:** Utility-first styling avoids the long-term maintenance cost of large, hand-written CSS files and keeps styling co-located with component markup, which scales better across many independently developed Applications' frontends.

**Alternatives considered:** CSS Modules, styled-components — both viable, but Tailwind was chosen for faster iteration and lower long-term stylesheet drift across multiple application frontends maintained by different teams.

**Trade-offs accepted:** Utility-class-heavy markup can reduce readability for contributors unfamiliar with Tailwind; mitigated through shared component abstractions rather than repeated utility strings.

## 4. Backend

### 4.1 FastAPI

**Role:** Primary web framework for Genesis Core's API surface and all Application backends.

**Why chosen:**
- Native async support is a direct requirement for a system whose Runtime must manage many concurrent, potentially long-running agent executions.
- Automatic OpenAPI schema generation directly supports the API-contract-first approach mandated by `02-System-Architecture.md` (Section 8.1, Contracts Before Implementations).
- Pydantic-based request/response validation gives Core a strong, enforced boundary for the data crossing the Applications ↔ Core dependency line (Section 6 of `02-System-Architecture.md`).

**Alternatives considered:**
| Alternative | Reason Not Chosen |
|---|---|
| Django / Django REST Framework | Heavier, more opinionated ORM-centric framework; less natural fit for an async, contract-first API surface |
| Flask | Lacks native async and built-in schema validation/generation, both of which are load-bearing requirements here |
| Node.js (Express/Nest) | Would fragment the backend language away from Python, which LangGraph and the broader agent/ML ecosystem are built around |

**Trade-offs accepted:** FastAPI's async model requires contributors to be disciplined about async/await usage throughout the Runtime and Workflow Engine; inconsistent use can silently degrade concurrency benefits.

**Scalability outlook:** FastAPI scales horizontally behind standard ASGI servers, and its schema-first design allows Core's public contracts to evolve in a versioned, backward-compatible way as new Applications are added.

### 4.2 Python

**Role:** Primary implementation language for Genesis Core and backend Applications.

**Why chosen:** Python is the dominant language across the agentic AI and ML ecosystem, including LangGraph itself. Choosing Python for Core avoids a language boundary between orchestration logic and the agent/tool ecosystem it must integrate with.

**Alternatives considered:** Go, TypeScript (backend) — both offer performance or type-safety advantages, but neither has comparable first-class support in the agent-framework ecosystem Genesis depends on.

**Trade-offs accepted:** Python's runtime performance and typing guarantees are weaker than compiled alternatives; this is mitigated through strict typing conventions (see `11-Coding-Standards.md`) and by isolating performance-sensitive paths behind replaceable interfaces (per the Replaceability principle in `00-GENESIS_CONTEXT.md`, Section 10).

## 5. Database & Persistence

### 5.1 PostgreSQL

**Role:** Primary persistent data store for Core Services, Memory System (long-term memory), and Application data.

**Why chosen:**
- Mature, well-understood relational semantics with strong consistency guarantees, which matter for auditable approval-gateway records and workflow execution history (see `02-System-Architecture.md`, Section 9, Observability).
- Native JSONB support allows semi-structured agent state and workflow graph data to be stored without requiring a separate document database.
- Extensive extension ecosystem (e.g., vector search extensions) supports future Memory System needs without a wholesale database migration.

**Alternatives considered:**
| Alternative | Reason Not Chosen |
|---|---|
| MongoDB | Weaker consistency guarantees and relational integrity, both important for auditability of approval decisions |
| MySQL | Comparable relational capability, but weaker native JSON/semi-structured data support and extension ecosystem |
| Dedicated vector database (e.g., standalone) | Premature at this stage; PostgreSQL's extension ecosystem can absorb this need without introducing a second persistence system early on |

**Trade-offs accepted:** A single relational store must be deliberately partitioned (schemas/namespaces) to avoid Applications' data models leaking into Core's tables, reinforcing rather than replacing the architectural separation defined in `02-System-Architecture.md`.

**Scalability outlook:** PostgreSQL supports read replicas, partitioning, and connection pooling strategies sufficient for Genesis's anticipated growth; if a specialized workload (e.g., large-scale vector search) eventually outgrows it, that concern can be isolated behind the Memory System's existing port (per Section 10 of `02-System-Architecture.md`) without affecting other subsystems.

### 5.2 SQLAlchemy

**Role:** ORM layer mediating access to PostgreSQL from Core and Application code.

**Why chosen:** Mature, explicit, and works well with FastAPI's async model via its async engine. Its Core/ORM dual-layer design allows low-level control where precision matters (e.g., workflow state persistence) while offering higher-level abstractions elsewhere.

**Alternatives considered:** Tortoise ORM, raw SQL — Tortoise is lighter-weight but less mature; raw SQL was rejected as the default because it would erode the schema-first discipline this project relies on for auditability.

**Trade-offs accepted:** SQLAlchemy's flexibility means teams must agree on conventions (see `11-Coding-Standards.md`) to avoid inconsistent query patterns across Core and Applications.

### 5.3 Alembic

**Role:** Schema migration tool paired with SQLAlchemy.

**Why chosen:** De facto standard for SQLAlchemy-based projects; supports versioned, reviewable migrations, which is essential given the auditability requirements described in `02-System-Architecture.md`.

**Alternatives considered:** Hand-written migration scripts — rejected due to lack of tooling for rollback and version tracking at scale.

## 6. Agent Framework

### 6.1 LangGraph

**Role:** Underlying execution model for the Workflow Engine's graph-based orchestration of multi-step and multi-agent workflows.

**Why chosen:**
- Explicit, graph-based representation of agent workflows aligns directly with the Explicit State principle in `02-System-Architecture.md` (Section 8.2) — workflow state is data, not hidden control flow.
- Native support for cycles, branching, and human-in-the-loop interrupts maps directly onto the Approval Gateway requirement (`00-GENESIS_CONTEXT.md`, Section 9).
- Active ecosystem alignment with the broader Python-based agentic tooling landscape.

**Alternatives considered:**
| Alternative | Reason Not Chosen |
|---|---|
| Custom-built orchestration engine | Rejected at this stage — reinventing graph execution, checkpointing, and interrupt handling would divert effort from Genesis's actual differentiation (Core abstractions) |
| AutoGen | Strong multi-agent conversation model, but less explicit about persisted, resumable execution state than LangGraph's graph/checkpoint model |
| CrewAI | Higher-level and more opinionated about agent "roles," which conflicts with Genesis Core's requirement to remain domain-agnostic |

**Trade-offs accepted:** Coupling the Workflow Engine's implementation to LangGraph's execution model creates a migration cost if LangGraph's design diverges significantly from Genesis's needs. This is mitigated by exposing LangGraph only behind the Workflow Engine's own port (per the Replaceability principle), so the Engine's public contract does not leak LangGraph-specific types to Applications.

**Scalability outlook:** LangGraph's checkpointing model supports long-running and resumable workflows, aligning with the Runtime's pause/resume requirement (`02-System-Architecture.md`, Section 5.2). Should orchestration needs outgrow LangGraph, the isolation described above allows the Workflow Engine's internal implementation to be replaced without changing Applications built against it.

## 7. Authentication

### 7.1 JWT

**Role:** Token format for authenticating requests across Genesis's API surface, mediated by Core Services (`02-System-Architecture.md`, Section 5.2).

**Why chosen:** Stateless verification allows Core Services to authenticate requests without a round-trip to a central session store on every call, which matters for a system expecting many concurrent agent-driven requests. Well-understood, broadly supported across FastAPI, Next.js, and third-party integrations.

**Alternatives considered:**
| Alternative | Reason Not Chosen |
|---|---|
| Server-side sessions | Requires a shared session store and adds a synchronous dependency to every authenticated request, at odds with the async, potentially long-running nature of agent workflows |
| OAuth2 as a full identity provider | Appropriate as a future addition for third-party/enterprise identity federation, but unnecessary complexity for the current stage; JWT can be issued after any OAuth2 flow is added later without architectural rework |

**Trade-offs accepted:** Token revocation is inherently harder with stateless JWTs; this is mitigated with short-lived access tokens and refresh-token rotation, defined further in `10-API-Standards.md`.

**Scalability outlook:** JWT scales naturally across horizontally scaled FastAPI instances with no shared session state required, and is compatible with a future move to a full identity provider (e.g., OAuth2/OIDC) without breaking existing token consumers.

## 8. Version Control

### 8.1 Git & GitHub

**Role:** Source control and collaboration platform for Genesis Core and all Applications.

**Why chosen:** Industry standard, with mature tooling for code review, CI/CD integration, and issue tracking — all of which are necessary for maintaining the architectural discipline (dependency rules, Separation Principle) described in `02-System-Architecture.md` through enforced review processes.

**Alternatives considered:** GitLab, Bitbucket — comparable capability; GitHub was chosen primarily for ecosystem familiarity and integration breadth with CI tooling and the broader open-source contributor base Genesis targets.

**Scalability outlook:** GitHub's branch protection, required reviews, and CI integration are used to enforce the dependency and separation rules from `02-System-Architecture.md` at the process level — see `12-Development-Workflow.md` for the concrete workflow built on top of this.

## 9. Cross-Cutting Considerations

### 9.1 Consistency With Architectural Principles

Every technology in this stack was evaluated against the same question: does this choice make the Separation Principle and dependency rules (`02-System-Architecture.md`, Sections 5–6) easier or harder to enforce? In each case above, the chosen technology was selected in part because it supports contract-first, replaceable design — not merely because of raw feature comparison.

### 9.2 Replaceability in Practice

Per `00-GENESIS_CONTEXT.md` (Section 10) and `02-System-Architecture.md` (Section 8.1), no technology listed here is assumed to be permanent. Each is bound to Core through an interface specific to its subsystem:

| Technology | Bound Through |
|---|---|
| PostgreSQL | Memory System / Core Services persistence ports |
| LangGraph | Workflow Engine port |
| JWT | Core Services authentication port |
| SQLAlchemy/Alembic | Persistence adapter layer, not exposed to Applications |

This ensures that any future change to this stack is a matter of implementing a new adapter, not a redesign of Genesis Core.

## 10. Relationship to Other Documents

This document justifies technology choices. It does not define:

- How these technologies are wired into Core's layered structure → see `02-System-Architecture.md`
- Concrete schema design → see `09-Database-Design.md`
- API conventions built on FastAPI → see `10-API-Standards.md`
- Coding conventions for Python/TypeScript → see `11-Coding-Standards.md`

Where a future technology change is proposed, it should be evaluated against Section 9.1's criterion and recorded here with the same structure used above (role, alternatives, trade-offs, scalability).