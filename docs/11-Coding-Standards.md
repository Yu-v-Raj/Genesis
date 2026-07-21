# Genesis — Coding Standards

## 1. Purpose

This document defines how code is written across Genesis: conventions for Python and TypeScript, how architectural rules from `02-System-Architecture.md` and `04-Folder-Structure.md` are enforced at the code level, documentation expectations within source files, testing philosophy, and what reviewers check for before approving a change.

This document governs *how* code is written. It does not redefine *where* code lives (`04-Folder-Structure.md`) or *what* the system's layers are responsible for (`02-System-Architecture.md`) — it assumes both as given and translates them into concrete conventions.

## 2. Architecture Rules Enforced at the Code Level

These rules restate, as enforceable coding conventions, the dependency rules from `02-System-Architecture.md`, Section 6, and the layering convention from `04-Folder-Structure.md`, Section 4.

| Rule | Enforcement |
|---|---|
| No `applications/*` import inside `core/*` | Static import-linting rule in CI (see `12-Development-Workflow.md`); a violation fails the build, not just a lint warning |
| `core/<subsystem>/domain/` imports nothing from that subsystem's own `infrastructure/` | Enforced via linting on import paths |
| `core/<subsystem>/infrastructure/` accesses external systems only through interfaces declared in that subsystem's `domain/` | Code review checklist item (Section 7) plus static analysis where feasible |
| Cross-subsystem calls within `core/` go through the target subsystem's `application/` or `contracts/` layer, never its `infrastructure/` | Import-linting rule, mirroring `04-Folder-Structure.md`, Section 10 |
| Plugins never import Runtime or Workflow Engine internals directly | Enforced by the Plugin System's sandboxing (`08-Plugin-System.md`, Section 6) and confirmed at review time |

A pull request that violates any rule in this table is treated as an architectural defect (`00-GENESIS_CONTEXT.md`, Section 13), not a style nitpick, regardless of whether the code otherwise functions correctly.

## 3. Python Standards

### 3.1 Style and Formatting

- Formatting is enforced by an automated formatter (applied uniformly, no manual style debates in review).
- Static type checking is required on every module; `Any` is permitted only at a documented, justified boundary (e.g., a genuinely dynamic plugin payload, per `08-Plugin-System.md`, Section 3.2) — never as a default escape hatch.
- Imports are organized: standard library, third-party, then first-party (`core.*` / `applications.*`), each group separated and alphabetized.

### 3.2 Typing Conventions

- All public functions and methods (anything crossing a subsystem or Application boundary) carry full type annotations, including return types.
- Pydantic models are the required shape for anything crossing an API boundary (`10-API-Standards.md`, Section 2.1) — plain dictionaries are not passed across contract boundaries.
- Enums (Python `Enum`/`StrEnum`) are used for any fixed set of values (e.g., lifecycle states, `06-Agent-Runtime.md`, Section 4.1), never bare strings compared by value.

### 3.3 Async Conventions

Because FastAPI's concurrency model depends on it (`03-Tech-Stack.md`, Section 4.1), any I/O-bound operation (database access, tool invocation, message passing) is implemented as `async`. A blocking call inside an async code path is treated as a defect, since it silently degrades the Runtime's concurrency guarantees (`06-Agent-Runtime.md`, Section 5).

### 3.4 Error Handling

- Exceptions raised within `core/` are typed, subsystem-specific exception classes (e.g., a `WorkflowEngineError` hierarchy), never bare `Exception`.
- Exceptions that should surface to an API consumer are translated at the `core/api/` boundary into the standard error shape defined in `10-API-Standards.md`, Section 5.1 — internal exception types are never leaked directly into an API response.
- Per the Fail Safe principle (`02-System-Architecture.md`, Section 8.4), catching an exception without either handling it meaningfully or re-raising a more specific one is not permitted; silent `except: pass` blocks are treated as defects.

### 3.5 Module and Package Naming

Follows `04-Folder-Structure.md`, Section 9: `snake_case` for packages and modules, matching subsystem names exactly (`workflow_engine`, `tool_manager`) so that a module's name and its architectural role are always in sync.

## 4. TypeScript Standards

### 4.1 Style and Formatting

- Formatting is enforced by an automated formatter, matching the "no manual style debate" posture applied to Python (Section 3.1).
- `strict` mode is enabled project-wide; `any` is disallowed except at explicitly justified boundaries (e.g., a third-party library without types), mirroring the Python typing discipline in Section 3.2.

### 4.2 Component Conventions

- React components are function components using Hooks; class components are not used for new code.
- Component files use `PascalCase.tsx` (per `04-Folder-Structure.md`, Section 9); one primary exported component per file.
- Props are always explicitly typed via an interface or type alias — never inferred implicitly from usage.

### 4.3 API Client Conventions

- Frontend code never hand-writes types for Core's or an Application's API responses; types are generated from the OpenAPI schema (`03-Tech-Stack.md`, Section 3.3), keeping frontend and backend contracts synchronized automatically per `10-API-Standards.md`, Section 8.1.
- API calls are centralized in a shared client layer (`packages/ts-shared`, see `04-Folder-Structure.md`, Section 6) rather than scattered `fetch` calls throughout component code.

### 4.4 State Management

Local component state uses React's built-in state primitives. Cross-component state that mirrors server data (e.g., an agent execution's current lifecycle state) is treated as server state — fetched and cached, not duplicated into ad hoc global client state that can drift from the source of truth in Core.

## 5. Documentation Practices Within Source Files

### 5.1 What Requires a Docstring/Comment

- Every public function, class, and module in `core/` requires a docstring describing its responsibility and its place within the subsystem's `domain/application/infrastructure` layering (`04-Folder-Structure.md`, Section 4).
- Any deviation from an architectural rule (Section 2) that has been explicitly reviewed and approved as an exception must be documented inline with a reference to the review decision — undocumented exceptions are not permitted.

### 5.2 What Does Not Belong in Comments

- Comments do not restate what code obviously does; they explain *why* a non-obvious decision was made (e.g., why a particular retry policy was chosen for a tool invocation).
- Comments never substitute for the architectural documentation set (`00`–`15`); a comment may reference a document (e.g., "see `06-Agent-Runtime.md`, Section 4.1") rather than re-explain the concept inline.

## 6. Testing Philosophy

### 6.1 Test Placement

Unit tests are colocated with the code they test within `core/` and `applications/` (per `04-Folder-Structure.md`, Section 8); tests spanning multiple subsystems or an Application-plus-Core boundary live under the root `tests/` directory (integration, contract, e2e).

### 6.2 What Must Be Tested

| Test Type | Required Coverage |
|---|---|
| Unit | Every `domain/` and `application/` module's public behavior, in isolation from `infrastructure/` |
| Integration | Interaction between a subsystem's `application/` layer and its real `infrastructure/` adapter (e.g., Memory System against a real PostgreSQL test instance) |
| Contract | Verifies Applications only exercise Core through published contracts (`04-Folder-Structure.md`, Section 8) — a contract test failing signals an architectural boundary violation, not just a functional bug |
| End-to-End | A full execution flow (`02-System-Architecture.md`, Section 7) exercised through the API layer, verifying an Application and Core together |

### 6.3 Test Independence

Tests never depend on execution order or shared mutable state between test cases. Each test constructs its own execution context and data, consistent with the Explicit State principle (`02-System-Architecture.md`, Section 8.2) applied to test design.

### 6.4 Testing Lifecycle-Sensitive Code

Any code touching the Runtime's lifecycle transitions (`06-Agent-Runtime.md`, Section 4.1) must include a test asserting that invalid transitions are rejected, not only that valid transitions succeed — the transition table's completeness is treated as a testable invariant, not just documentation.

## 7. Code Review Expectations

### 7.1 Review Checklist

Every pull request review confirms, in this order:

1. **Architectural compliance** — no violation of Section 2's rules, and no new dependency that crosses an ownership boundary from `04-Folder-Structure.md`, Section 5 or `09-Database-Design.md`, Section 3.2.
2. **Contract stability** — if an API or plugin contract changed, it follows the versioning rules in `10-API-Standards.md`, Section 3, or `08-Plugin-System.md`, Section 5.3.
3. **Test coverage** — new behavior is covered per Section 6.2's table; lifecycle-sensitive changes include the invariant test from Section 6.4.
4. **Documentation consistency** — docstrings/comments per Section 5, and any change affecting a document in the `docs/` set (`00`–`15`) includes a corresponding update in the same pull request.
5. **Style and typing** — automated formatting and type-checking pass; manual style debate is out of scope for review since Sections 3.1/4.1 delegate this to tooling.

### 7.2 Reviewer Authority

A reviewer may block a pull request solely on architectural grounds (item 1 above), even if the code is otherwise correct and well-tested. Architectural compliance is not negotiable at review time on the basis of short-term convenience, consistent with `00-GENESIS_CONTEXT.md`, Section 13.

### 7.3 Disagreement Resolution

Where a reviewer and author disagree about whether a change violates an architectural rule, the question is resolved by referring to the specific document and section defining that rule (`02-System-Architecture.md`, `04-Folder-Structure.md`, or this document) — not by informal precedent. If the documents genuinely do not address the situation, the resolution is to propose a documentation update first, then proceed with the code change, per the same principle described in `04-Folder-Structure.md`, Section 13.

## 8. Relationship to Other Documents

This document defines coding-level conventions and review expectations. It intentionally does not define:

- Why the underlying technologies were chosen → see `03-Tech-Stack.md`
- The dependency rules being enforced here → see `02-System-Architecture.md`, Section 6, and `04-Folder-Structure.md`, Section 10
- The CI/CD process that automates enforcement of Section 2 and Section 7 → see `12-Development-Workflow.md`

Where a future convention appears to conflict with the architectural rules in Section 2, this document defers to `02-System-Architecture.md` until this document is formally revised to match.