# Genesis — Database Design

## 1. Purpose

This document defines the philosophy, organization, and evolution strategy for Genesis's persistence layer. It establishes how data is partitioned across Core subsystems and Applications, how migrations are governed, and how the schema is expected to scale — without yet committing to concrete table definitions. Concrete schemas are introduced incrementally, as each subsystem's implementation matures, and must conform to the boundaries and principles established here.

This document assumes familiarity with `02-System-Architecture.md` (layering and dependency rules), `03-Tech-Stack.md` (PostgreSQL/SQLAlchemy/Alembic rationale), and `07-Memory-System.md` (long-term memory persistence requirements).

## 2. Database Philosophy

### 2.1 One Physical Database, Many Logical Boundaries

Genesis uses a single PostgreSQL instance (see `03-Tech-Stack.md`, Section 5.1) as its primary data store, but this is a deployment decision, not a license to blur ownership. The Separation Principle (`00-GENESIS_CONTEXT.md`, Section 5) applies to the database exactly as it applies to code: Core's tables and an Application's tables are logically distinct, independently reasoned about, and never joined across the ownership boundary at the query level.

### 2.2 Schema as a Reflection of Architecture

The database schema is expected to mirror the subsystem boundaries defined in `02-System-Architecture.md`, Section 5, not the convenience of any single query. A table belongs to exactly one subsystem or Application; if a design would require a table to serve two owners, that is a signal the boundary has been drawn incorrectly, not a signal to add a shared table.

### 2.3 Data Outlives Code

Because Genesis emphasizes auditability (`02-System-Architecture.md`, Section 9) and explicit state (`02-System-Architecture.md`, Section 8.2), the database is treated as a durable record of what happened — execution checkpoints, approval decisions, memory writes — not merely a cache of current application state. Schema design favors append-friendly, historically traceable structures over destructive updates wherever auditability is relevant.

## 3. Schema Organization

### 3.1 Namespace-Level Partitioning

The database is organized into PostgreSQL schemas (namespaces) that mirror ownership boundaries at the filesystem level (`04-Folder-Structure.md`, Section 4–5):

| Schema Namespace | Owner | Contains |
|---|---|---|
| `core_runtime` | Runtime subsystem | Execution lifecycle records, checkpoints |
| `core_memory` | Memory System | Long-term memory records (see `07-Memory-System.md`, Section 5) |
| `core_workflow` | Workflow Engine | Workflow graph definitions and execution history |
| `core_plugins` | Plugin System | Plugin registration, manifest, and lifecycle records (see `08-Plugin-System.md`, Section 4) |
| `core_approval` | Approval Gateway | Approval requests and recorded decisions |
| `core_services` | Core Services | Configuration, authN/authZ, audit logs |
| `app_<application_name>` | Each Application | Application-specific data models |

This mirrors, at the schema level, the same subsystem decomposition established architecturally, so that a table's schema prefix alone indicates its ownership — the same principle applied to directories in `04-Folder-Structure.md`, Section 9 (Naming Conventions).

### 3.2 Cross-Namespace Access Rules

- A table in `core_*` may never be queried directly by an Application; Applications access Core data only through Core's API contracts (`02-System-Architecture.md`, Section 6), never through direct SQL access to `core_*` schemas.
- A table in `app_<application_name>` is never queried by Core. Core has no awareness of Application schema contents, consistent with the Separation Principle.
- Cross-subsystem references within `core_*` (e.g., a `core_runtime` checkpoint referencing a `core_memory` record) are expressed as opaque identifiers (foreign-key-like references by ID), never as cross-schema joins that assume knowledge of another subsystem's internal table structure.

## 4. Entity Boundaries

Rather than defining concrete tables, this section defines the entity *categories* each schema namespace is responsible for, establishing the boundary each future schema document/migration must respect.

| Namespace | Entity Category | Boundary Rule |
|---|---|---|
| `core_runtime` | Execution instances, lifecycle transitions, checkpoints | Contains no reference to what a workflow graph node *means* — only its identifier and position |
| `core_memory` | Long-term memory records (`record_id`, `owner_execution_id`, `application_id`, `key`, `payload`, `metadata`) | `payload` is always opaque (JSONB); the Memory System never defines its internal shape |
| `core_workflow` | Workflow graph definitions, execution history | Stores graph structure and history, not the domain logic executed at each node |
| `core_plugins` | Plugin manifests, registration state, permission grants | Stores declared permissions (`08-Plugin-System.md`, Section 3.2) and lifecycle state, not plugin implementation code |
| `core_approval` | Approval requests, decisions, reviewer identity references | Stores the fact and outcome of a review, not the domain rationale for why an action was classified important (that classification logic lives in code, per `05-Agent-OS.md`, Section 6) |
| `core_services` | Configuration entries, auth credentials/tokens metadata, audit log entries | Stores cross-cutting operational data only |
| `app_<name>` | Whatever entities the Application's domain requires | Fully owned and defined by the Application team; Core imposes no shape requirement beyond standard conventions (Section 6) |

Entity boundaries are enforced at review time (see `12-Development-Workflow.md`): a proposed table that would require Core to encode Application-specific concepts (e.g., a `prd_status` column inside a `core_*` table) is rejected as an architectural violation, not merged with a caveat.

## 5. Migration Strategy

### 5.1 Tooling

Migrations are managed with Alembic (see `03-Tech-Stack.md`, Section 5.3), with one migration environment per major schema namespace grouping (Core's `core_*` namespaces share a single migration history; each Application maintains its own).

### 5.2 Migration Principles

| Principle | Rationale |
|---|---|
| Additive by default | New columns/tables are preferred over destructive changes; this preserves the durable-record philosophy in Section 2.3 |
| Backward-compatible within a release cycle | A migration must not break a currently-deployed version of Core's API contracts (`02-System-Architecture.md`, Section 8.1) |
| Reviewed against entity boundaries | Every migration is reviewed against the ownership table in Section 4 before merge |
| No cross-namespace migrations in a single change | A migration touching both a `core_*` namespace and an `app_*` namespace is split into separate, independently reviewable migrations |
| Reversible where feasible | Every migration includes a downgrade path unless the change is fundamentally irreversible (e.g., data-destructive cleanup), in which case this is called out explicitly in the migration's description |

### 5.3 Ownership of Migration History

Each namespace owner (a Core subsystem team or an Application team, per `04-Folder-Structure.md`, Section 4–5 ownership boundaries) owns its own migration history and is responsible for its review, consistent with the broader ownership model.

## 6. Indexing Principles

Concrete indexes are defined alongside each namespace's concrete schema as it is implemented, but the following principles govern all indexing decisions across Genesis:

| Principle | Application |
|---|---|
| Index for known access patterns, not speculative ones | E.g., `core_memory` is indexed for key-based and metadata-filtered lookup (`07-Memory-System.md`, Section 6) because those are defined retrieval modes; speculative indexes for unimplemented modes (e.g., vector similarity, Section 8) are deferred until that capability ships |
| Composite indexes reflect ownership-scoped queries | Because Applications never query across `application_id` boundaries (`07-Memory-System.md`, Section 6), indexes on shared tables like `core_memory` lead with `application_id` to keep Application-scoped queries efficient without requiring cross-partition scans |
| Avoid over-indexing append-heavy tables | Tables capturing history (checkpoints, approval decisions, audit logs) favor a small number of high-value indexes (e.g., by execution ID and timestamp) over comprehensive indexing, since write throughput matters more than exhaustive query flexibility for these tables |
| JSONB fields indexed selectively | Structured `payload`/`metadata` JSONB fields (Section 4) are indexed only on the specific keys actually queried by defined retrieval modes, not indexed generically across their full structure |

## 7. Scalability Considerations

| Concern | Approach |
|---|---|
| Growth of execution/checkpoint history | `core_runtime` and `core_workflow` history tables are designed for partitioning by time range (e.g., monthly) as volume grows, without changing the logical schema exposed to the Runtime |
| Growth of long-term memory | `core_memory` can scale via read replicas for retrieval-heavy workloads, and is a natural candidate for partitioning by `application_id` as the number of Applications grows |
| Multi-tenant / multi-organization deployment | Addressed by extending `core_services` configuration and authZ entities, not by changing the entity boundaries in Section 4 |
| Read/write separation | FastAPI's async support (`03-Tech-Stack.md`, Section 4.1) and SQLAlchemy's async engine allow read-heavy retrieval paths (e.g., memory retrieval) to be routed to replicas independently of write-heavy paths (checkpointing), once replica topology is introduced |
| Future non-relational needs | Any workload that outgrows PostgreSQL's model (e.g., large-scale vector search, per `07-Memory-System.md`, Section 8) is isolated behind the relevant subsystem's existing port, so it can be served by a different backing store without changing entity boundaries elsewhere |

## 8. Future Evolution

This document deliberately stops short of defining concrete tables, columns, and constraints. As each subsystem's implementation matures, this document (or a dedicated per-namespace schema reference) will be extended to include:

- Concrete table definitions per namespace (Section 3.1), reviewed against the entity boundaries in Section 4.
- Concrete index definitions per table, governed by the principles in Section 6.
- A formal partitioning plan once volume in `core_runtime`/`core_workflow` approaches thresholds identified in Section 7.
- Vector storage schema additions to `core_memory`, once the future retrieval mode described in `07-Memory-System.md`, Section 8, is implemented.

Any such addition must be evaluated against Sections 2–4 of this document before being merged, so that concrete schema growth continues to reflect — rather than erode — Genesis's architectural boundaries.

## 9. Relationship to Other Documents

This document defines database philosophy, organization, and evolution strategy. It intentionally does not define:

- Why PostgreSQL/SQLAlchemy/Alembic were chosen → see `03-Tech-Stack.md`, Section 5
- The Memory System's logical record shape and retrieval semantics → see `07-Memory-System.md`
- The review process through which migrations and schema changes are approved → see `12-Development-Workflow.md`

Where a future concrete schema appears to conflict with the entity boundaries in Section 4, this document takes precedence until formally revised.