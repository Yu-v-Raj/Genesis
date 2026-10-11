# Memory Runtime

A `MemoryRecord` is immutable and agent-owned: ID, agent ID, content (≤ 10,000
characters), a small `MemoryKind` (`fact`, `note`, `preference`, `context`), timestamps,
metadata, and tags.

`MemoryManager` owns validation, ownership checks, CRUD orchestration, and typed EventBus
events (`memory.created`, `memory.updated`, `memory.deleted`, `memory.retrieved`). It
depends on the `MemoryProvider` port.

## Storage (v0.13)

The application uses `SqlAlchemyMemoryProvider`: memories live in the `agent_memories`
table (migration `0004`), survive restarts, and are deleted with their Agent
(`ON DELETE CASCADE`). `InMemoryProvider` remains for unit tests. Search is a
case-insensitive substring match over content, tags, and metadata within one Agent.

## Use in conversations (v0.13)

Before each chat turn, the Agent's own memories are added to the model context as one
system message, after the Agent's instructions:

- only memories whose `agent_id` is the chatting Agent's (never another Agent's);
- newest first, at most 20 and about 4,000 characters, with a note when older memories
  are left out;
- framed as background information, not instructions;
- assembled per turn and never written to the conversation.

There is no relevance ranking yet: every memory of the Agent is a candidate until the
budget is used. Memories are only created explicitly (Memory page or API); the Agent does
not write memories by itself.

## API

`GET /api/memory`, `GET/PATCH/DELETE /api/memory/{memory_id}`,
`GET/POST /api/agents/{agent_id}/memory`, `GET /api/agents/{agent_id}/memory/search`.
Agent-scoped reads and mutations enforce ownership.

## Not yet implemented

Semantic or vector retrieval, relevance ranking, automatic memory writing by Agents,
per-user or shared memory scopes, and retention policies. Anything stored as a memory is
sent to the configured LLM provider with every message to that Agent, so do not store
secrets in memories.
