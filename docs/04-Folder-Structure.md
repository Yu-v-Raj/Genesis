# Genesis — Folder Structure

## 1. Purpose

This document defines the repository layout for Genesis: where code lives, why it lives there, what may depend on what, and the naming conventions contributors are expected to follow. It operationalizes, at the filesystem level, the dependency rules and layer responsibilities defined in `02-System-Architecture.md`.

A contributor should be able to determine a file's architectural role (Core, Application, Infrastructure) from its path alone, without reading its contents.

## 2. Repository Model

Genesis is organized as a single **monorepo** containing Core, all Applications, shared tooling, and documentation. A monorepo was chosen over per-application repositories because:

- Core's contracts and every Application consuming them can be reviewed and versioned together, making breaking changes visible at pull-request time rather than discovered later across disconnected repositories.
- Shared tooling (linting, CI, type generation) is defined once and applied uniformly, which is difficult to guarantee across separate repositories.

Should the ecosystem of Applications grow large enough that independent release cadences become necessary, individual Applications can be extracted into their own repositories without restructuring Core, since Applications already depend on Core only through its published contracts (`02-System-Architecture.md`, Section 6).

## 3. Top-Level Layout

```
genesis/
├── core/                    # Genesis Core (Agent Operating System) — see Section 4
├── applications/            # Applications built on Genesis Core — see Section 5
├── packages/                # Shared libraries used by both Core and Applications — see Section 6
├── infra/                   # Infrastructure-as-code, deployment, environment config — see Section 7
├── docs/                    # Documentation set (this file's own directory)
├── scripts/                 # Repository-wide developer tooling and automation
├── tests/                   # Cross-cutting/system-level tests (see Section 8)
├── .github/                 # CI/CD workflows, issue/PR templates
├── pyproject.toml           # Root Python project/workspace configuration
├── package.json             # Root Node/TypeScript workspace configuration
├── README.md
└── LICENSE
```

## 4. `core/` — Genesis Core

`core/` contains the Agent Operating System exclusively. Nothing in this directory may reference an Application, either by import or by domain-specific naming.

```
core/
├── runtime/                 # Agent execution lifecycle (start, pause, resume, terminate)
│   ├── domain/               # Runtime domain models and interfaces (ports)
│   ├── application/          # Use-case/service layer orchestrating runtime behavior
│   └── infrastructure/       # Concrete adapters (e.g., process/thread execution backends)
│
├── workflow_engine/          # Graph-based multi-step/multi-agent orchestration
│   ├── domain/
│   ├── application/
│   └── infrastructure/       # LangGraph-backed adapter implementing the Workflow Engine port
│
├── memory/                   # Short-term and long-term memory abstractions
│   ├── domain/
│   ├── application/
│   └── infrastructure/       # PostgreSQL-backed adapter implementing the Memory port
│
├── plugin_system/             # Plugin loading, sandboxing, and lifecycle management
│   ├── domain/
│   ├── application/
│   └── infrastructure/
│
├── tool_manager/               # Tool registration and mediated invocation
│   ├── domain/
│   ├── application/
│   └── infrastructure/
│
├── communication/              # Inter-agent and agent-human messaging
│   ├── domain/
│   ├── application/
│   └── infrastructure/         # Message transport adapter
│
├── approval_gateway/            # Human-approval checkpoint enforcement
│   ├── domain/
│   ├── application/
│   └── infrastructure/
│
├── core_services/                # Cross-cutting: config, logging, authN/authZ
│   ├── config/
│   ├── logging/
│   └── auth/
│
├── api/                          # FastAPI application exposing Core's public contracts
│   ├── routers/
│   ├── schemas/                   # Pydantic request/response models (the public contract surface)
│   └── dependencies/
│
└── contracts/                     # Versioned public interfaces consumed by Applications
    ├── runtime_contract.py
    ├── workflow_contract.py
    ├── memory_contract.py
    ├── plugin_contract.py
    └── tool_contract.py
```

**Ownership boundary:** `core/` is owned by the Genesis Core maintainers. Changes here require review against the dependency rules and Separation Principle (`02-System-Architecture.md`, Sections 5–6) as a first-class review criterion, not merely functional correctness.

**Internal layering convention:** Each subsystem under `core/` follows the same three-tier internal split — `domain/` (interfaces and models, no external dependencies), `application/` (orchestration logic depending only on domain), and `infrastructure/` (concrete adapters depending on domain, never the reverse). This mirrors the hexagonal style defined in `02-System-Architecture.md`, Section 3, at the subsystem level.

## 5. `applications/` — Applications Built on Genesis

```
applications/
└── product_manager/            # AI Product Manager — first reference application (v0.1)
    ├── backend/
    │   ├── agents/               # Application-specific agent definitions
    │   ├── workflows/            # Application-specific workflow graph definitions
    │   ├── prompts/               # Domain prompts (PRD generation, market research, etc.)
    │   ├── models/                 # Application-specific data models
    │   └── api/                     # Application-specific FastAPI routers, consuming core/contracts
    │
    ├── frontend/
    │   ├── app/                    # Next.js app directory
    │   ├── components/
    │   ├── lib/                     # API client generated from Core's OpenAPI schema
    │   └── styles/
    │
    └── README.md                    # Application-specific documentation entry point
```

Every future application follows the same `applications/<application_name>/{backend,frontend}` shape. An application directory may depend on `core/contracts/` and `packages/`, and never on another application's directory.

**Ownership boundary:** Each application directory is owned by the team responsible for that application. Application teams may not modify `core/` to accommodate their application; changes to Core contracts follow the review process defined in `12-Development-Workflow.md`.

## 6. `packages/` — Shared Libraries

```
packages/
├── py-shared/                  # Shared Python utilities usable by Core and Applications
│   └── (e.g., common validation helpers, generic error types)
│
└── ts-shared/                  # Shared TypeScript utilities/types usable by all frontends
    └── (e.g., generated API types from Core's OpenAPI schema)
```

Code belongs in `packages/` only if it is genuinely domain-agnostic and usable by more than one consumer. A utility used by exactly one Application belongs inside that Application's own directory, not in `packages/`.

## 7. `infra/` — Infrastructure as Code

```
infra/
├── docker/                     # Dockerfiles for core, each application, and shared services
├── compose/                    # Local development docker-compose definitions
├── migrations/                  # Alembic migration environment (references core/memory and core_services schemas)
├── k8s/                          # Kubernetes manifests/Helm charts (future production deployment)
└── environments/                  # Environment-specific configuration (dev, staging, production)
```

`infra/` never contains business logic. It configures and deploys what already exists in `core/` and `applications/`.

## 8. `docs/`, `scripts/`, `tests/`

```
docs/                            # This documentation set (00–15)
scripts/                          # Dev environment bootstrap, codegen, lint/format runners
tests/
├── integration/                  # Cross-subsystem tests within Core
├── contract/                      # Tests verifying Applications only use published Core contracts
└── e2e/                             # End-to-end tests spanning an Application and Core together
```

Unit tests live alongside the code they test within `core/` and `applications/` (see `11-Coding-Standards.md`). `tests/` at the root is reserved for tests that span multiple subsystems or repositories-in-spirit (Core + an Application), where colocation with a single module would be misleading.

## 9. Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Python packages/directories | `snake_case` | `workflow_engine/`, `tool_manager/` |
| Python modules/files | `snake_case.py` | `runtime_contract.py` |
| TypeScript/React directories | `kebab-case` | `product-manager/` (within an app's frontend routes) |
| React components | `PascalCase.tsx` | `WorkflowGraphView.tsx` |
| Application directories | `snake_case`, matches the application's identifier | `product_manager/` |
| Core subsystem directories | Matches the subsystem name from `02-System-Architecture.md`, Section 5.2 | `memory/`, `plugin_system/` |
| Contract files | `<subsystem>_contract.py` | `memory_contract.py` |
| Migration files (Alembic) | `<timestamp>_<description>.py`, auto-generated | `20260101_add_workflow_checkpoints.py` |

Consistency between architectural vocabulary (`02-System-Architecture.md`) and directory names is treated as a review requirement: if a subsystem is renamed conceptually, its directory is renamed in the same change.

## 10. Dependency Rules at the Filesystem Level

The dependency rules from `02-System-Architecture.md`, Section 6, are enforced at the folder level as follows:

1. **No file under `applications/` may be imported by any file under `core/`.** Enforced via import linting in CI (see `12-Development-Workflow.md`).
2. **No file under `core/<subsystem>/infrastructure/` may be imported directly by `applications/`.** Applications import only from `core/contracts/` and `core/api/`.
3. **No file under `core/<subsystem>/domain/` may import from that subsystem's own `infrastructure/`.** Enforced by the internal layering convention in Section 4.
4. **No cross-subsystem imports within `core/` bypass a subsystem's `application/` or `contracts/` layer.** E.g., `workflow_engine/` may call `memory/`'s contract, never reach into `memory/infrastructure/` directly.
5. **`infra/` never imports application or Core business logic** — it only references configuration and deployment artifacts (Dockerfiles, manifests).

```
applications/*        ──▶ core/contracts, core/api, packages/*
core/<subsystem>/application ──▶ core/<subsystem>/domain
core/<subsystem>/infrastructure ──▶ core/<subsystem>/domain
core/<subsystem A> ──▶ core/<subsystem B>/contracts   (never subsystem B's domain/infrastructure directly)
```

## 11. Adding a New Application

To add a new Application, a contributor:

1. Creates `applications/<application_name>/{backend,frontend}` following the structure in Section 5.
2. Depends only on `core/contracts/`, `core/api/`, and `packages/`.
3. Adds no new directories under `core/` to support the new Application.

If building a new Application appears to require a change inside `core/`, that change must be justified as a generic Core capability (per the Separation Principle, `00-GENESIS_CONTEXT.md`, Section 5) and proposed independently of the Application's own pull request.

## 12. Adding a New Core Subsystem

Adding a new subsystem to `core/` is a rarer, higher-scrutiny change than adding an Application. It requires:

1. A corresponding update to `02-System-Architecture.md` describing the subsystem's responsibility and its position in the dependency graph.
2. A new `core/<subsystem_name>/{domain,application,infrastructure}` directory following Section 4's internal layering convention.
3. A corresponding entry in `core/contracts/` if the subsystem exposes a public interface to Applications.

## 13. Relationship to Other Documents

This document defines where things live. It does not define:

- Why each subsystem exists or how it fits architecturally → see `02-System-Architecture.md`
- Coding conventions within files → see `11-Coding-Standards.md`
- The review/CI process enforcing the rules in Section 10 → see `12-Development-Workflow.md`
- Database schema contents within `infra/migrations/` → see `09-Database-Design.md`

Any proposed deviation from this structure should be raised as a revision to this document before being implemented, so that the folder structure remains a reliable map of the architecture rather than drifting from it.