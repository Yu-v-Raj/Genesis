# 🤖 Genesis

## Your AI Agent Operating System

> **Genesis is a modular AI Agent Operating System designed to provide the infrastructure required to build, run, coordinate, observe, and scale intelligent AI agents.**

Genesis brings together **Agents, LLMs, Tools, Memory, Execution, Workflows, Events, Realtime Communication, and Observability** into one extensible platform.

---

## 📖 Overview

Modern AI agents are more than an LLM wrapped around a prompt. A production-grade agent needs infrastructure for reasoning, actions, memory, execution, coordination, communication, and monitoring.

Genesis provides:

- 🤖 **Agent Runtime** — agent identity and lifecycle
- 🧠 **LLM Runtime** — provider-independent model interaction
- 🔧 **Tool Runtime** — capabilities agents can execute
- 🧠 **Memory Runtime** — agent context and knowledge
- ⚙️ **Execution Runtime** — units of work and execution state
- 🔄 **Workflow Runtime** — multi-step task coordination
- 📡 **EventBus** — typed event-driven communication
- ⚡ **Realtime Layer** — WebSocket-based live updates
- 📊 **Observability** — logs, events, health, and runtime visibility

Genesis is being built as a **foundation for autonomous and multi-agent systems**, rather than as a single-purpose AI application.

---

# 🎯 Why Genesis?

Building an intelligent agent requires connecting many systems:

```text
LLM
 │
 ├── Tools
 ├── Memory
 ├── Execution
 ├── Workflows
 ├── Other Agents
 ├── Events
 └── Observability
```

Without clear boundaries, these components quickly become tightly coupled.

Genesis addresses this through:

- 🧩 **Modularity**
- 🔌 **Provider independence**
- 🏗️ **Clean Architecture**
- 🔄 **Composable execution**
- 📡 **Event-driven communication**
- ⚡ **Realtime visibility**
- 🧪 **Testable infrastructure**
- 🚀 **Extensible runtimes**

---

# ✨ Core Features

## 🤖 Agent Runtime

Genesis provides a foundation for managing AI agents and their lifecycle.

```text
Created
   ↓
Initialized
   ↓
Idle
   ↓
Thinking
   ↓
Executing
   ↓
Waiting
   ↓
Completed
   ↓
Failed / Stopped
```

Agents are platform actors that can eventually reason through LLMs, use tools, access memory, and participate in workflows.

---

## 🧠 LLM Runtime

Genesis abstracts model providers behind a common provider interface.

### Currently integrated

- OpenAI provider
- Google Gemini provider
- Provider registry
- Provider-neutral message/request/response models
- Generation settings
- Usage tracking
- Sanitized provider errors
- LLM lifecycle events

### Current Gemini flow

```text
Genesis LLM Runtime
        ↓
  Gemini Provider
        ↓
 google-genai SDK
        ↓
 Gemini 3.6 Flash
        ↓
 Generated Response
```

The provider abstraction allows additional LLM providers to be added without coupling the rest of Genesis to a specific SDK.

---

## 🔧 Tool Runtime

Tools give agents capabilities outside the LLM.

### Built-in tools

- `echo`
- `calculator`
- `uuid`
- `random_number`
- `delay`

The Tool Runtime provides:

- Tool registry
- Tool discovery
- Validation
- Execution
- Execution history
- Tool events
- Capability metadata

### Tool-calling concept

```text
User
 ↓
LLM
 ↓
Tool Call
 ↓
Tool Runtime
 ↓
Tool Result
 ↓
LLM
 ↓
Final Response
```

The LLM decides **what should happen** while the Tool Runtime executes the capability.

---

## 🧠 Memory Runtime

Genesis provides a provider-based memory abstraction for storing agent context and knowledge.

### Current capabilities

- Agent-scoped memory
- Create / update / delete
- Deterministic search
- Ownership validation
- Bounded in-memory provider
- Memory lifecycle events
- Memory dashboard

The architecture is designed so persistent and vector-based providers can be added later without changing the core memory API.

---

## ⚙️ Execution Runtime

Execution represents a concrete unit of work.

It provides:

- Execution lifecycle management
- Execution context
- Cancellation/progress support
- Bounded execution history
- Tool-backed execution
- Execution events

```text
Execution
   ↓
Task
   ↓
Tool / Agent / Runtime
   ↓
Result
```

Execution is separate from Agent lifecycle so that **"an agent exists"** and **"an agent is performing a job"** remain different concepts.

---

## 🔄 Workflow Runtime

The Workflow Runtime coordinates multiple tasks and their dependencies.

```text
        A
       /       B   C
       \ /
        D
```

A workflow:

1. Validates the task graph
2. Determines ready tasks
3. Dispatches executable tasks
4. Tracks task state
5. Waits for results
6. Reevaluates dependencies
7. Starts newly-ready tasks
8. Handles failures and blocking

```text
Workflow
   ↓
Tasks
   ↓
Dependencies
   ↓
Coordinator
   ↓
Execution / Tools / Agents
   ↓
Results
   ↓
Next Ready Tasks
```

This provides deterministic coordination around the probabilistic reasoning of LLMs.

---

# 📡 Event-Driven Architecture

Genesis uses a typed **EventBus** as a communication backbone.

Examples:

```text
agent.created
agent.started
agent.completed

tool.started
tool.completed
tool.failed

memory.created
memory.updated
memory.deleted
memory.retrieved

workflow.created
workflow.started
workflow.completed
workflow.failed

execution.started
execution.completed

llm.requested
llm.completed
llm.failed
```

The EventBus keeps subsystems decoupled while providing a unified runtime activity stream.

---

# ⚡ Realtime Communication

Genesis exposes runtime activity through WebSockets.

```text
Runtime Component
       ↓
    EventBus
       ↓
 WebSocket Manager
       ↓
 /ws/events
       ↓
 Next.js Frontend
```

The frontend follows:

```text
REST
 ↓
Initial State

WebSocket
 ↓
Incremental Updates
```

---

# 📊 Observability

Genesis includes a dedicated observability layer for understanding what the platform is doing.

### Includes

- Structured logging
- Event history
- Error logs
- Heartbeat monitoring
- System health
- Runtime metrics
- Live event streams
- Realtime notifications

---

# 🏗️ System Architecture

```text
                           ┌─────────────────┐
                           │      User       │
                           └────────┬────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │      Agent      │
                           └────────┬────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │   LLM Runtime   │
                           │ OpenAI / Gemini │
                           └────────┬────────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                         ▼                     ▼
                  ┌─────────────┐       ┌─────────────┐
                  │   Workflow  │       │    Memory   │
                  │   Runtime   │       │   Runtime   │
                  └──────┬──────┘       └─────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │  Execution  │
                  │   Runtime   │
                  └──────┬──────┘
                         │
                  ┌──────┴──────┐
                  ▼             ▼
            ┌──────────┐   ┌──────────┐
            │   Tools  │   │  Agents  │
            └──────────┘   └──────────┘

                         ┌─────────────┐
                         │   EventBus  │
                         └──────┬──────┘
                                │
                  ┌─────────────┴─────────────┐
                  ▼                           ▼
          ┌──────────────┐             ┌──────────────┐
          │Observability │             │   Realtime   │
          └──────────────┘             │  WebSockets  │
                                       └──────────────┘
```

---

# 🔄 Agent Execution Flow

The eventual complete Genesis interaction follows:

```text
User Request
     ↓
    Agent
     ↓
    LLM
     ↓
Reason / Decide
     ↓
Workflow / Execution
     ↓
 ┌───┼────────────┐
 ↓   ↓            ↓
Tool Memory   Other Agent
 └───┼────────────┘
     ↓
   Result
     ↓
    LLM
     ↓
Final Response
```

> **LLMs provide reasoning; runtimes provide reliable infrastructure.**

---

# 🛠️ Technology Stack

| Category | Technology |
|---|---|
| Programming Language | Python 3.12 |
| Backend | FastAPI |
| Architecture | Clean Architecture |
| Dependency Injection | Service Registry / DI |
| Frontend | React 19 |
| Frontend Framework | Next.js 15 |
| Language | TypeScript |
| Styling | Tailwind CSS v4 |
| UI Components | shadcn/ui |
| Animations | Framer Motion |
| Realtime | WebSockets |
| LLM Providers | OpenAI / Google Gemini |
| Gemini SDK | google-genai |
| API Documentation | FastAPI / Swagger |
| Testing | Pytest |
| Version Control | Git / GitHub |

---

# 📁 Project Structure

```text
Genesis/
│
├── backend/
│   └── app/
│       ├── core/
│       │   ├── agents/
│       │   ├── api/
│       │   ├── execution_runtime/
│       │   ├── llm_runtime/
│       │   ├── memory_runtime/
│       │   ├── observability/
│       │   ├── tool_runtime/
│       │   ├── workflow_runtime/
│       │   └── core_services/
│       └── main.py
│
├── frontend/
│   ├── app/
│   │   ├── agents/
│   │   ├── memory/
│   │   ├── monitoring/
│   │   ├── tools/
│   │   ├── workflows/
│   │   └── page.tsx
│   ├── components/
│   ├── hooks/
│   ├── services/
│   └── types/
│
├── docs/
│   ├── 16-Tool-Runtime.md
│   ├── 17-Memory-Runtime.md
│   ├── 18-Workflow-Runtime.md
│   ├── 19-LLM-Runtime.md
│   └── ...
│
├── .env.example
├── pyproject.toml
└── README.md
```

---

# 🖥️ Platform Dashboard

Genesis includes dedicated interfaces for inspecting and interacting with the platform.

- 🏠 **Dashboard** — system overview
- 🤖 **Agents** — agent identity and lifecycle
- 🔧 **Tools** — discovery and execution
- 🧠 **Memory** — agent memory management
- 🔄 **Workflows** — workflow coordination
- 📊 **Monitoring** — events, logs, health, and realtime activity

---

# 🧪 Verification

Genesis is developed incrementally with automated and manual verification.

Current verified capabilities include:

- Core platform services
- Observability
- Realtime WebSockets
- Agent lifecycle
- Execution Runtime
- Tool Runtime
- Memory Runtime
- Workflow Runtime
- LLM Runtime
- OpenAI/Gemini provider discovery
- Real Gemini generation through `gemini-3.6-flash`

Latest LLM Runtime verification:

```text
106 backend tests passed
compileall passed
git diff --check passed
Real Gemini generation → HTTP 200 ✅
```

Example:

```text
Input:
"What is 2 + 2? Reply with only the number."

Gemini:
"4"
```

---

# 🚀 Getting Started

## 1. Clone the repository

```bash
git clone https://github.com/Yu-v-Raj/Genesis
cd Genesis
```

## 2. Configure the backend

Create `.env` from `.env.example`.

Example:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.6-flash
GEMINI_TIMEOUT_SECONDS=30
```

> Never commit `.env` or API keys to GitHub.

## 3. Install backend dependencies

```bash
python -m pip install -e .
```

## 4. Start the backend

```bash
python -m uvicorn backend.app.main:app --reload
```

Backend:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## 5. Start the frontend

From `frontend`:

```bash
npm install
npm run dev
```

Frontend:

```text
http://localhost:3000
```

---

# 📚 Documentation

Detailed subsystem documentation is available in `docs/`.

Current runtime documentation includes:

- Tool Runtime
- Memory Runtime
- Workflow Runtime
- LLM Runtime

---

# 🗺️ Roadmap

### ✅ Completed

- Core Platform
- Observability
- Realtime Communication
- Agent Identity & Lifecycle
- Execution Runtime Foundation
- Tool Runtime
- Memory Runtime
- Workflow Runtime
- LLM Runtime Foundation
- OpenAI Provider
- Gemini Provider

### 🔜 Planned

- Agent ↔ LLM integration
- Tool calling through LLM decisions
- Context assembly
- Persistent memory providers
- Vector memory / semantic retrieval
- RAG
- Multi-agent coordination
- Advanced workflow execution
- Streaming LLM responses
- Production deployment
- Authentication and authorization
- Distributed execution
- Production-grade persistence

---

# 🧠 Design Philosophy

> **Build the infrastructure around intelligence, not just the intelligence itself.**

An LLM can reason, but it does not by itself provide reliable execution, persistent state, tool management, workflow coordination, lifecycle management, observability, realtime communication, or provider abstraction.

Genesis exists to provide those capabilities.

---

# 📌 Project Status

**Genesis is actively under development.**

The platform foundation is operational. The next major stage is connecting the existing runtimes into a complete intelligent agent execution loop.

```text
Agents
  +
LLMs
  +
Tools
  +
Memory
  +
Execution
  +
Workflows
  +
Events
  +
Observability
       ↓
  Intelligent Agents
```

---

## ⭐ If you find Genesis interesting

Explore the architecture, runtime implementations, documentation, and development history in this repository.

---

# 📜 License

Add your chosen license here.
