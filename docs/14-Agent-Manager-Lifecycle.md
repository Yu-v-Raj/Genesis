# Agent Manager & Lifecycle

## Purpose

The `AgentManager` is the Phase B application service for creating Agent Runtime
records, validating lifecycle transitions, and maintaining each agent's ephemeral
`AgentContext`. It is application-agnostic and does not execute agents, tools,
workflows, or LLM calls.

## Boundaries

- `AgentRegistry` owns immutable Agent metadata snapshots and lookup.
- `AgentManager` owns lifecycle orchestration and runtime-only contexts.
- `AgentContext` is in-memory process state, not persistent memory or history.
- The Event Bus publishes lifecycle facts without coupling consumers to the manager.

## Lifecycle

```text
CREATED -> INITIALIZING -> IDLE -> RUNNING
                                   |-> WAITING -> RUNNING
                                   |-> PAUSED  -> RUNNING
                                   |-> COMPLETED
                                   |-> FAILED

Any state -> STOPPED
```

Invalid transitions raise `AgentLifecycleError`. `initialize_agent()` performs the
short synchronous `CREATED -> INITIALIZING -> IDLE` sequence because initialization
has no asynchronous execution work in this milestone.

## Runtime Context

Every managed Agent receives a context with a session ID, current lifecycle state,
optional current task, temporary variables, runtime metadata, and timestamps. The
context is updated alongside valid lifecycle transitions and removed when an agent is
deleted.

## Observability and API

The manager publishes `agent.created`, `agent.initialized`, `agent.started`,
`agent.paused`, `agent.resumed`, `agent.completed`, `agent.failed`, `agent.stopped`,
`agent.deleted`, and `agent.context_updated` events. The REST adapter exposes
creation, deletion, lifecycle controls, metadata updates, and context inspection and
updates under `/api/agents`. It remains a thin transport layer over the manager.

## Future Work

Future execution services may add work to the initialization and running states,
provide a controlled transition into `WAITING`, and subscribe to lifecycle events.
They must preserve the ownership boundaries above and must not make the Agent Manager
responsible for planning, scheduling, or execution infrastructure.
