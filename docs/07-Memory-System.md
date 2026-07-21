# Genesis — Memory System

## 1. Purpose

This document defines the Memory System: the Agent OS subsystem responsible for giving agents a place to store, retrieve, and reason over context across a single execution and across executions over time. Where `06-Agent-Runtime.md` defines how an agent's execution is scheduled and checkpointed, this document defines what "state" and "context" mean from the Memory System's point of view, and how they are persisted, retrieved, and eventually superseded.

This document is application-agnostic. The Memory System has no concept of what is being remembered — a "PRD draft" and a "competitor list" are, to the Memory System, indistinguishable structured records belonging to some agent's context.

## 2. Design Principles

| Principle | Meaning for Memory |
|---|---|
| Explicit State (`02-System-Architecture.md`, 8.2) | Memory contents are always representable as inspectable, persisted data — never held only in an agent's in-process variables |
| Replaceability (`00-GENESIS_CONTEXT.md`, 10) | The Memory System's storage backend is swappable behind a stable contract, without Applications or the Runtime needing to change |
| Application-Agnosticism (`00-GENESIS_CONTEXT.md`, 5) | The Memory System stores structured records identified by keys and metadata; it assigns no domain meaning to their contents |
| Auditability (`02-System-Architecture.md`, 9) | Every write to long-term memory is attributable to a specific agent execution and timestamp |
| Boundedness | Working memory has an enforced size/scope limit per execution, preventing unbounded context growth from degrading Runtime performance |

## 3. Memory Layers

The Memory System exposes two distinct layers, each with a different lifetime and access pattern:

```
┌────────────────────────────────────────────────────────────┐
│                      Memory System                          │
│                                                               │
│   ┌───────────────────────┐      ┌────────────────────────┐ │
│   │   Working Memory        │      │   Long-Term Memory       │ │
│   │   (per-execution)        │      │   (cross-execution)      │ │
│   │                          │      │                          │ │
│   │  - Scoped to one          │      │  - Persisted independent │ │
│   │    agent execution          │      │    of any single         │ │
│   │  - Backed by fast,           │      │    execution's lifetime  │ │
│   │    ephemeral storage          │      │  - Backed by PostgreSQL  │ │
│   │  - Cleared on execution        │      │    (see 03-Tech-Stack)   │ │
│   │    completion (unless            │      │  - Queryable by key,       │ │
│   │    promoted, see 4.3)             │      │    metadata, or (future)   │ │
│   │                                      │      │    vector similarity       │ │
│   └───────────────────────┘      └────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### 3.1 Working Memory

Working memory holds the context an agent needs during a single execution: the current task input, intermediate reasoning artifacts, tool results received so far, and the current position within the workflow graph (mirrored from the Runtime's checkpoint, see `06-Agent-Runtime.md`, Section 4.2).

Working memory is scoped strictly to one execution. It is not visible to other concurrently running agents unless explicitly shared through the Communication Layer (`06-Agent-Runtime.md`, Section 6) — the Memory System itself does not broker cross-agent visibility.

### 3.2 Long-Term Memory

Long-term memory holds records intended to outlive a single execution: prior outputs, accumulated knowledge an application wants agents to draw on in future executions, and historical decisions. Long-term memory is always written explicitly — nothing is promoted from working memory to long-term memory without an explicit write call through the Memory System's contract.

## 4. Memory Lifecycle

### 4.1 Lifecycle States

```
   ┌─────────┐     write      ┌──────────┐     read      ┌───────────┐
   │ Created  │──────────────▶│ Persisted │◀─────────────▶│ Retrieved │
   └─────────┘                └────┬─────┘                └───────────┘
                                    │
                                    │ supersede / delete
                                    ▼
                              ┌───────────┐
                              │ Archived /  │
                              │ Deleted     │
                              └───────────┘
```

| State | Meaning |
|---|---|
| Created | A memory record has been constructed by an agent but not yet written |
| Persisted | The record has been durably written (working memory: ephemeral store; long-term memory: PostgreSQL) |
| Retrieved | The record has been read back by an agent execution; retrieval does not change the record's state |
| Archived / Deleted | The record has been explicitly superseded or removed, per an Application's retention policy |

### 4.2 Working Memory Lifecycle

Working memory is created when an execution enters the Running state (`06-Agent-Runtime.md`, Section 4) and is cleared when the execution reaches a terminal state (Completed or Failed), unless explicitly promoted to long-term memory beforehand (Section 4.3). This bounds working memory's lifetime to the lifetime of a single execution, keeping its storage requirements predictable regardless of how many past executions the system has accumulated.

### 4.3 Promotion to Long-Term Memory

An agent (through Application-defined workflow logic) may explicitly promote a working-memory record to long-term memory before its execution completes. Promotion is always an explicit, logged action — the Memory System never promotes data on an agent's behalf based on inferred importance, since inferring importance would require domain knowledge the Memory System is not permitted to hold (Section 1).

### 4.4 Archival and Deletion

Long-term memory records may be archived (retained but excluded from default retrieval) or deleted, according to retention rules defined by the Application, not the Memory System itself. The Memory System enforces only the mechanics of archival/deletion (soft-delete flags, retention timestamps) and the auditability of who/what triggered it — it does not decide when data should be retired.

## 5. Persistence

Long-term memory is persisted in PostgreSQL (see `03-Tech-Stack.md`, Section 5.1), behind the Memory System's own port, following the layering convention defined in `04-Folder-Structure.md`, Section 4. A long-term memory record is stored with the following structural shape, expressed independent of any application's domain fields:

| Field | Purpose |
|---|---|
| `record_id` | Unique identifier for the memory record |
| `owner_execution_id` | The agent execution that created the record (auditability) |
| `application_id` | Which Application's data this record belongs to (data partitioning, see `04-Folder-Structure.md`, Section 4 ownership boundaries) |
| `key` | Application-defined lookup key |
| `payload` | Structured content (stored as JSONB), opaque to the Memory System |
| `metadata` | Application-defined tags/attributes usable for filtering |
| `created_at` / `superseded_at` | Timestamps supporting the lifecycle in Section 4 |

Working memory, by contrast, is backed by fast ephemeral storage appropriate to the Runtime's execution-context lifetime (Section 3.1) — its persistence guarantees are scoped to "survive a pause/resume within an execution's lifetime" (`06-Agent-Runtime.md`, Section 5.2), not "survive indefinitely."

## 6. Retrieval

The Memory System exposes retrieval through its contract in three modes, all application-agnostic:

| Mode | Description |
|---|---|
| Key-based lookup | Retrieve a specific record by its known key |
| Metadata filtering | Retrieve records matching Application-defined metadata attributes |
| Similarity search (future) | Retrieve records semantically related to a query, via vector similarity (Section 8) |

Retrieval never crosses `application_id` boundaries (Section 5): an Application cannot retrieve another Application's long-term memory records, reinforcing the ownership boundaries established in `04-Folder-Structure.md`.

## 7. Context Management

"Context" — the subset of memory an agent actually receives as input at a given point in execution — is assembled by the Memory System on request from the Runtime's Execution Context Manager (`06-Agent-Runtime.md`, Section 3), not decided unilaterally by the Memory System itself. Context assembly follows these rules:

1. **Boundedness.** The Memory System enforces a configurable maximum size for assembled context, preventing unbounded growth of working memory from degrading execution performance (Section 2, Boundedness principle).
2. **Explicit composition.** Which long-term records are pulled into a given execution's working memory is determined by an explicit retrieval call (Section 6, invoked by Application-defined workflow logic) — the Memory System does not silently inject long-term data into working memory.
3. **No cross-execution leakage.** Context assembled for one execution is never visible to a concurrently running, unrelated execution, even within the same Application.

## 8. Future Vector Memory Integration

The current long-term memory implementation supports key-based and metadata-filtered retrieval (Section 6). Vector-based similarity retrieval is a planned extension, not yet part of the default implementation, and is designed for so that its addition requires no change to the Memory System's public contract:

- PostgreSQL's extension ecosystem (see `03-Tech-Stack.md`, Section 5.1) allows vector storage and similarity search to be added to the existing persistence layer without introducing a second database system.
- Embedding generation is treated as an Application concern (since it depends on domain-specific content), while storage and similarity query execution remain a Memory System infrastructure concern.
- The `payload` field's storage shape (Section 5) already accommodates arbitrary structured data, including precomputed embeddings, without a schema migration being required at the contract level.

When implemented, similarity search will be exposed as an additional retrieval mode (Section 6) behind the same Memory System port used by key-based and metadata-filtered retrieval — consistent with the Replaceability and Contracts Before Implementations principles (`02-System-Architecture.md`, Section 8.1).

## 9. Relationship to Other Documents

This document defines the Memory System's architecture, lifecycle, and retrieval semantics. It intentionally does not define:

- How Runtime checkpoints reference working memory during pause/resume → see `06-Agent-Runtime.md`, Section 4.2
- The concrete database schema and indexing strategy for long-term memory tables → see `09-Database-Design.md`
- API-level request/response shapes for memory read/write operations → see `10-API-Standards.md`

Where a future document appears to describe memory behavior inconsistent with the layer definitions in Section 3 or the lifecycle in Section 4, this document takes precedence until formally revised.