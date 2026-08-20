# Tool Runtime

## Purpose

Tool Runtime is Genesis's deterministic execution boundary for registered capabilities. It contains no AI providers, browser, filesystem, Python, memory, or workflow execution.

## Architecture

Executions may submit a lightweight `Task` to `ToolManager`. The manager records bounded task history, delegates resolution and invocation to `ToolExecutor`, and uses `ToolRegistry` for immutable Tool declarations. The Executor is independent of FastAPI and emits typed events through the existing Event Bus.

## Task model

A Task records its UUID, optional Execution UUID, Tool name, status, timestamps, immutable metadata, and terminal ToolResult. It is deliberately minimal, allowing future queues, retries, parallel work, and workflows without introducing a Task Runtime now.

## Built-ins

`echo`, `calculator` (AST-based safe arithmetic; never `eval`), `uuid`, `random_number`, and bounded `delay` are registered at startup.

## Events and REST

Tool Runtime publishes `tool.registered`, `tool.executed`, `tool.completed`, `tool.failed`, `task.created`, `task.completed`, and `task.failed`. Existing Event History, realtime broadcasting, logs, and monitoring consume them automatically. REST endpoints are `GET /api/tools`, `GET /api/tools/{name}`, `POST /api/tools/execute`, `GET /api/tools/history`, and `GET /api/tools/capabilities`.

## Future integration

Future memory, workflow, LLM, and plugin layers can register Tools or submit Tasks through this boundary while keeping permission enforcement and transport adapters outside Tool implementations.
