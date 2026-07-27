# Genesis — Frontend Context

This document is the permanent frontend architecture reference for the Genesis project. Any Claude conversation working on the Genesis frontend should read this file first instead of re-deriving project context.

---

## 1. Project Overview

Genesis is an Agent Operating System, not simply an AI application. It provides the runtime, memory, orchestration, and plugin infrastructure required to build and operate autonomous AI applications, rather than being a single-purpose AI product itself.

The backend is already implemented with a modular architecture. The frontend's job is to expose and operate that backend — not to define or redesign it.

---

## 2. Backend Overview

The backend is organized into the following core modules:

- **Dependency Injection Container** — Manages the construction and wiring of services and their dependencies throughout the system.
- **Service Registry** — Tracks all registered services, their availability, and their metadata.
- **Runtime Lifecycle Manager** — Controls startup, shutdown, and state transitions of the Genesis runtime.
- **Event Bus** — Handles publish/subscribe messaging between system components.
- **Tool Manager** — Manages registration, discovery, and invocation of tools available to agents.
- **Plugin System** — Enables extending Genesis with additional capabilities via installable plugins.
- **Memory Framework** — Provides persistent and contextual memory capabilities for agents.
- **Workflow Engine** — Orchestrates multi-step or multi-agent workflows.
- **System API** — Exposes system state and operations to external clients, including the frontend.

---

## 3. Current System API

The following endpoints are currently available:

| Endpoint | Description |
|---|---|
| `GET /api/system/health` | Returns overall system health status. |
| `GET /api/system/runtime` | Returns current runtime lifecycle state. |
| `GET /api/system/services` | Returns the list of registered services and their status. |
| `GET /api/system/tools` | Returns the list of registered tools available to agents. |
| `GET /api/system/plugins` | Returns the list of installed and available plugins. |
| `GET /api/system/memory` | Returns memory framework status and summary data. |
| `GET /api/system/workflows` | Returns active and available workflows. |

---

## 4. Frontend Goals

The Genesis frontend should be modern, clean, responsive, developer-focused, highly polished, and production quality. It should feel closer to Vercel, Linear, GitHub, and Cursor than a traditional admin dashboard.

---

## 5. Tech Stack

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS v4
- shadcn/ui
- Lucide React
- Framer Motion

Additional libraries will only be introduced intentionally and with explicit approval.

---

## 6. Design Principles

- Dark-first theme
- Minimal interface
- Spacious layout
- Consistent spacing
- Accessible components
- Smooth animations
- Responsive by default
- Excellent typography
- Professional developer-tool aesthetic

---

## 7. Frontend Architecture

High-level planned folder structure:

```
app/
components/
features/
hooks/
lib/
api/
styles/
theme/
```

This structure should remain minimal and should not be over-engineered.

---

## 8. Coding Standards

- TypeScript everywhere
- Reusable components
- No duplicated UI
- Keep business logic outside components
- Consistent naming
- Clean folder organization
- Follow existing architecture

---

## 9. Things Claude MUST NOT Do

- Do not redesign project architecture.
- Do not change backend APIs.
- Do not introduce state-management libraries without approval.
- Do not introduce unnecessary dependencies.
- Do not generate mock APIs.
- Do not over-engineer.

---

## 10. Future Roadmap

- Dashboard
- Tool Manager UI
- Plugin UI
- Memory UI
- Workflow Visualization
- Agent Console
- Monitoring
- Settings