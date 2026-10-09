# Agent Persistence (v0.11)

Agent definitions and conversation sessions are stored in the database named by
`DATABASE_URL` and restored when the backend starts. This document describes what is
stored, how it is restored, and what is deliberately **not** resumable.

## Architecture

```text
API routers ──> AgentConfigurationService / AgentInteractionService
                          │
                 AgentManager (lifecycle, sessions, restoration)
                          │
       AgentRegistry (write-through cache)     SessionRepository port
                          │                            │
                 AgentRepository port                  │
                          │                            │
   agent_runtime/infrastructure/sqlalchemy_repositories.py (SQLAlchemy, async)
                          │
              backend/app/database (engine factory, Alembic helpers)
```

- **Ports** (`agent_runtime/application/repositories.py`) are plain ABCs; the domain
  records (`Agent`, `AgentSession`, `Message`) never import SQLAlchemy.
- **Adapters**: `SqlAlchemyAgentRepository` / `SqlAlchemySessionRepository` (production),
  `InMemory*Repository` (default when nothing is wired, used by unit tests).
- **Composition**: `backend/app/main.py` creates the engine, verifies the schema, wires the
  SQL adapters, restores Agents, and disposes the engine on shutdown.
- **Errors**: adapters raise `PersistenceError` (HTTP 503, retryable) or
  `PersistenceConflictError` (HTTP 409). Messages never contain the database URL,
  credentials, or stored content.

## What is stored

| Table | Contents |
|---|---|
| `agents` | id, name, description, type, tags, metadata, LLM provider + model name, allowed tools, instructions, timestamps, restoration status, optimistic-lock `version` |
| `agent_sessions` | id, agent_id (FK, cascade delete), message_count, title (first user message), timestamps |
| `agent_session_messages` | session_id (FK, cascade), `position` (unique per session), role, content, interaction_id, tool_call_id, tool_name, tool_status, tool_calls (JSON), created_at |

Not stored: API keys (they stay in `.env`), system instructions as messages (they are
assembled per turn from the Agent), runtime context, executions, tool task history,
events, memory records, and workflows.

`tool_calls` keeps tool-call arguments and provider continuation data (for example Gemini
thought signatures) because the LLM needs them when history is replayed. The session API
never returns them; it exposes tool names and outcomes only.

## Agent restoration policy

Status is stored as a *restoration category*, not the live status:

| Live status | Stored as | After restart |
|---|---|---|
| CREATED, INITIALIZING | `created` | CREATED (user finishes setup) |
| IDLE, RUNNING, PAUSED, WAITING, COMPLETED, FAILED | `idle` | CREATED → initialized through the normal lifecycle → IDLE |
| STOPPED | `stopped` | STOPPED |

Per-turn IDLE ↔ RUNNING flips are never written, so an Agent is never restored as
RUNNING. Restoration publishes the usual lifecycle events plus `agent.restored`. If
re-initialization fails, the Agent stays CREATED with its definition and sessions intact
and can be initialized again (the UI offers *Finish setup*).

## Session guarantees

- An Agent has many sessions. Chat continues the **active** session (the most recently
  used one) unless a `session_id` is given; `POST /api/agents/{id}/sessions` starts a new,
  empty one. A session ID that belongs to another Agent is a 404.
- A turn (user message, assistant tool calls, tool results, final reply) is stored in **one
  transaction** after the interaction finishes. Failed or interrupted turns store nothing.
- The append is a compare-and-set on `message_count`, backed by the unique
  `(session_id, position)` constraint: if another writer changed the session first, the
  turn is rejected with 409 instead of interleaving.
- Within one process, one interaction per Agent runs at a time (unchanged from v0.10D).
- Agent writes use optimistic locking (`version`): a stale writer gets 409, not a silent
  overwrite.

## Not resumable

Persistence covers definitions and **completed** conversation history. It does not resume
work that was in flight:

- An interaction interrupted by a crash or restart is lost; its turn was never stored and
  the user re-sends the message.
- Executions and workflow runs are durable since v0.12 (see
  `21-Durable-Executions-and-Workflows.md`); work cut off mid-step is recovered or held
  for a decision rather than resumed blindly.
- Tool task history, memory records, and the event stream are still in memory.

## Operations

```bash
# Apply migrations (uses DATABASE_URL from the environment or .env)
alembic upgrade head

# Show the current revision / check models against migrations
alembic current
alembic check

# Review the SQL without connecting
alembic upgrade head --sql
```

The backend refuses to start if it cannot reach the database or the schema is not at
the latest migration, and prints which one (with any password hidden).

**Recovery**: if the database is temporarily unavailable, requests that need storage
return 503 and nothing partial is written; retry once it is back. If startup fails with a
migration mismatch, run `alembic upgrade head`. Deleting an Agent deletes its sessions.

## Testing

`backend/conftest.py` gives every test its own SQLite database, produced by the real
Alembic migrations, so tests never touch your `DATABASE_URL`. To also run the
persistence adapter tests against PostgreSQL, point `GENESIS_TEST_POSTGRES_URL` at a
**disposable** database (it is reset for every test):

```bash
GENESIS_TEST_POSTGRES_URL=postgresql+asyncpg://user@localhost/genesis_test python -m pytest backend/app/core/agent_runtime/infrastructure -q
```

## Known limitations

- The registry cache assumes a single backend process (as do WebSockets). Multiple
  workers would need the registry to read through to the database.
- Long sessions are replayed to the LLM in full; there is no context-window trimming yet.
- No authentication: anyone who can reach the API can read stored conversations.
