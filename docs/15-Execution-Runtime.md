# Execution Runtime

## Purpose

Execution Runtime provides the independent lifecycle for work requested from an Agent. It deliberately contains no LLM, tool, memory, or workflow integration; the v0.5 Phase A executor only validates the end-to-end pipeline deterministically.

## Architecture

`execution_runtime` follows the Core domain/application/infrastructure boundary. `ExecutionManager` owns lifecycle transitions, active runtime contexts, background tasks, history writes, and typed event publication. `ExecutionHistory` is a bounded, newest-first in-memory store whose interface can be backed by a database later. `ExecutionExecutor` is the replaceable deterministic worker.

## Domain model

`Execution` is immutable metadata: UUID identifiers, status, timestamps, calculated duration, terminal result/error, and immutable metadata. Updates use copy-on-write. `ExecutionContext` is explicitly runtime-only and holds the current step, variables, metadata, and cancellation request. `ExecutionResult` captures a terminal status, output, duration, logs, and metadata.

## Lifecycle

The supported states are `pending`, `queued`, `starting`, `running`, `completed`, `failed`, and `cancelled`. Terminal states cannot transition. The deterministic executor sleeps for roughly two seconds and returns `Execution completed successfully.`

An execution is valid only for an existing initialized Agent that is not stopped. Starting or finishing an execution never changes its Agent lifecycle: one Agent may have any number of independent executions.

## Events

The runtime publishes typed observability events: `execution.created`, `execution.queued`, `execution.started`, `execution.progress`, `execution.completed`, `execution.failed`, and `execution.cancelled`. Existing Event Bus subscribers, event history, logger, and realtime gateway receive them normally.

## REST API

- `POST /api/agents/{id}/execute` creates and schedules an execution (202).
- `GET /api/executions` lists bounded history, newest first.
- `GET /api/executions/{execution_id}` reads one execution.
- `GET /api/agents/{id}/executions` lists an Agent's executions.
- `POST /api/executions/{execution_id}/cancel` requests cancellation.

## Future integration

Later phases can supply tool, LLM, memory, and workflow-aware executors behind the `ExecutionExecutor` boundary without changing execution metadata, lifecycle ownership, history, or REST contracts.
