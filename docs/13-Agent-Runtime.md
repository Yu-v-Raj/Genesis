# Agent Runtime Foundation

## What is an Agent?

In Genesis, an Agent is a process-like Core record: a uniquely identified unit with lifecycle state, immutable descriptive metadata, tags, and timestamps. It is deliberately not a language model, prompt, tool bundle, or autonomous loop.

This distinction lets Genesis manage agent identity and lifecycle consistently before choosing any reasoning provider or execution strategy. An Agent can later be backed by an LLM, deterministic program, human-operated process, or another adapter without changing its Core identity.

## Domain and Registry

`agent_runtime.domain.Agent` is an immutable record with copy-on-write status and metadata transitions. `AgentStatus` models the lifecycle from `created` through terminal states such as `completed`, `failed`, and `stopped`.

`AgentRegistry` is an injected, in-memory application service. It owns only Agent metadata:

- registration, lookup, listing, removal, existence, and count;
- status and metadata transitions;
- publication of typed lifecycle events through the existing Event Bus.

It does not import FastAPI, LLM providers, tools, memory, workflows, or scheduling code.

## Events and API

Registry changes publish `agent.registered`, `agent.removed`, `agent.status_changed`, and `agent.metadata_updated`. Existing Event History and real-time subscribers receive these events automatically; no second event system exists.

The read-only API exposes:

- `GET /api/agents`
- `GET /api/agents/{id}`
- `GET /api/agents/count`

## Future execution

Future phases may resolve the same `AgentRegistry` through the Service Registry to attach execution state, scheduling, model adapters, tools, memory, or workflows. Those capabilities must remain separate application services; this foundation intentionally manages only the process record and its observable lifecycle.
