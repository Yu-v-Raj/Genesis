# Agent Manager & Lifecycle

## Purpose

The `AgentManager` creates Agent Runtime records, validates lifecycle transitions, and
maintains each agent's ephemeral `AgentContext` and conversation session. LLM and tool
coordination lives in `AgentInteractionService`; configuration validation lives in
`AgentConfigurationService`.

## Boundaries

- `AgentRegistry` owns immutable Agent metadata snapshots and lookup.
- `AgentManager` owns lifecycle orchestration and runtime-only contexts.
- `AgentContext` is in-memory process state, not persistent memory or history.
- The Event Bus publishes lifecycle facts without coupling consumers to the manager.

## Lifecycle

Agents are long-lived and reusable (v0.10D). `RUNNING` means "an interaction is in
progress" and is owned by `AgentInteractionService`, not by callers.

```text
CREATED -> INITIALIZING -> IDLE <-> RUNNING     (each chat turn: IDLE -> RUNNING -> IDLE)

Any non-stopped state -> STOPPED                 (terminal)
```

- `initialize_agent()` performs the synchronous `CREATED -> INITIALIZING -> IDLE`
  sequence. `POST /api/agents` with `"initialize": true` does this in one call.
- LLM failures, tool failures, safety rejections, and the tool-iteration limit return
  the Agent to `IDLE`; they never fail the Agent.
- `finish_interaction()` leaves an Agent unchanged if it left `RUNNING` mid-turn (for
  example it was stopped), so a late response cannot undo a stop.
- `POST /start`, `/pause`, `/resume` are retired and return `409`: entering `RUNNING`
  without an interaction left Agents unable to chat. `PAUSED`, `WAITING`, `COMPLETED`,
  and `FAILED` remain in the enum for compatibility but are not reachable through the API.

Invalid transitions raise `AgentLifecycleError` (`409`). `AgentUnavailableError`, a
subclass, carries a user-facing reason when a chat cannot start.

## Configuration (v0.10E-B)

An Agent's `llm_model`, `allowed_tools`, and `instructions` are validated by
`AgentConfigurationService` against the live LLM and Tool runtimes before they are
stored: the provider must be registered, the model must be one that provider offers,
and every tool must be registered. A provider without an API key is accepted; its
models report `metadata.configured: false` and chat returns `503` with the missing
setting. `PATCH /api/agents/{id}/configuration` changes these fields while the Agent is
`CREATED` or `IDLE` and publishes `agent.configuration_updated` with the changed field
names only. `instructions` are sent as a system message each turn and are never stored
in the session or emitted in events.

## Sessions

An Agent has any number of conversation sessions; chat continues the active (most
recently used) one unless a `session_id` is passed, and `POST /api/agents/{id}/sessions`
starts a new one. Each completed turn (user message, assistant tool calls, tool results,
final reply) is stored atomically when the turn ends, so failed requests leave no partial
history. Every message records its `interaction_id`; tool results record `tool_name` and
`tool_status`. The session endpoints return these display fields but never tool-call
arguments or provider metadata.

## Persistence and restoration (v0.11)

Agent definitions and sessions are stored in the database (`docs/20-Agent-Persistence.md`).
Status is stored only as a restoration category (`created`, `idle`, `stopped`); at startup
`AgentManager.restore_agents()` brings `idle` Agents back through
`CREATED -> INITIALIZING -> IDLE`, so no Agent is ever restored as `RUNNING`.

## Runtime Context

Every managed Agent receives a context with a session ID, current lifecycle state,
optional current task, temporary variables, runtime metadata, and timestamps. The
context is updated alongside valid lifecycle transitions and removed when an agent is
deleted.

## Observability and API

The manager publishes `agent.created`, `agent.initialized`, `agent.started`,
`agent.status_changed` (every transition, including the return to `IDLE` after a chat),
`agent.configuration_updated`,
`agent.paused`, `agent.resumed`, `agent.completed`, `agent.failed`, `agent.stopped`,
`agent.deleted`, and `agent.context_updated` events. The REST adapter exposes
creation, deletion, lifecycle controls, metadata updates, and context inspection and
updates under `/api/agents`. It remains a thin transport layer over the manager.

## Future Work

Future execution services may add work to the initialization and running states,
provide a controlled transition into `WAITING`, and subscribe to lifecycle events.
They must preserve the ownership boundaries above and must not make the Agent Manager
responsible for planning, scheduling, or execution infrastructure.
