# Workflow Runtime

Genesis Workflow Runtime is the dependency-aware coordination layer. A workflow is an immutable definition and evolving snapshot of named workflow tasks; it is not an Execution Runtime task and does not reimplement agents, tools, or memory.

Tasks form a validated directed acyclic graph. A task becomes ready only after every dependency completes successfully. The coordinator dispatches independent ready tasks concurrently through the existing Tool Runtime, records their outputs on the workflow task, then reevaluates dependents. This supports sequential pipelines and parallel fan-out/fan-in safely.

Workflow states are `created`, `queued`, `running`, `paused`, `completed`, `failed`, and `cancelled`; task states are `pending`, `ready`, `running`, `completed`, `failed`, `cancelled`, and `blocked`. Invalid IDs, self-dependencies, missing dependencies, duplicate IDs, and cycles are rejected before storage. A failed task blocks unfinished dependents and fails its workflow. Pause prevents new dispatches; already-running underlying tool work is not forcibly paused. Cancellation stops future dispatch and marks unfinished tasks cancelled without altering completed results.

The initial action is `tool`, with `tool_name` and `tool_arguments`. Tool execution is delegated to `ToolRuntimeManager`; no tool implementation or validation is duplicated. Workflow events use the existing EventBus and thereby flow to event history, logs, realtime, and monitoring.

API: `POST /api/workflows`, `GET /api/workflows`, `GET/DELETE /api/workflows/{id}`, `POST /api/workflows/{id}/start|pause|resume|cancel`, and `GET /api/workflows/{id}/tasks|history`.

Future extensions may add retry and fallback policies, conditionals, loops, scheduling, approval gates, LLM planning, and multi-agent workflows.
