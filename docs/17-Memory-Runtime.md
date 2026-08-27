# Memory Runtime

Genesis v0.7A provides an agent-owned, provider-agnostic memory foundation. A `MemoryRecord` is immutable and contains an ID, agent ID, content, small `MemoryKind`, timestamps, metadata, and tags.

`MemoryManager` owns validation, ownership checks, CRUD orchestration, and typed EventBus publication. It depends on `MemoryProvider`, whose asynchronous CRUD, list, search, and count contract is independent of transport and storage technology. The initial `InMemoryProvider` has bounded capacity, evicts the oldest retained item, and returns newest-first deterministic results.

API endpoints are `GET /api/memory`, `GET/PATCH/DELETE /api/memory/{memory_id}`, `GET/POST /api/agents/{agent_id}/memory`, and `GET /api/agents/{agent_id}/memory/search`. Agent-scoped reads and mutations enforce ownership. Events are `memory.created`, `memory.updated`, `memory.deleted`, and `memory.retrieved`, flowing through the established EventBus, history, logs, and realtime bridge.

This release deliberately has no persistence, embeddings, vector/semantic search, RAG, LLM integration, or shared cross-agent memory. PostgreSQL, Redis, and vector-backed implementations can replace the provider without changing the manager or REST API.
