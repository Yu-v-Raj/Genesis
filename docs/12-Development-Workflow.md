# Genesis — Development Workflow

## 1. Purpose

This document defines the engineering workflow contributors follow from initial planning through merged, deployed code. It is the process layer that enforces, mechanically and procedurally, the architectural rules established in `02-System-Architecture.md`, the folder/ownership boundaries in `04-Folder-Structure.md`, and the coding and review standards in `11-Coding-Standards.md`.

Where those documents define *what* the rules are, this document defines *when in the process* they are checked and by *whom*.

## 2. Workflow Overview

```
Planning ─▶ Design Review ─▶ Implementation ─▶ Testing ─▶ Documentation
   │                                                              │
   └──────────────────────────▶ Pull Request ◀───────────────────┘
                                     │
                          Automated Checks (CI)
                                     │
                          Architectural Review
                                     │
                              Human-Approval Gate
                             (for Core changes)
                                     │
                                  Merge
                                     │
                                Release
```

Every change to Genesis — Core or Application — passes through this sequence. The depth of review at each stage scales with the change's blast radius (Section 6).

## 3. Planning

### 3.1 Issue Classification

Before implementation begins, a proposed change is classified as one of:

| Classification | Definition |
|---|---|
| Core change | Touches any `core/` subsystem, its contracts, or its database namespace (see `04-Folder-Structure.md`, Section 4; `09-Database-Design.md`, Section 3.1) |
| Application change | Touches only a single `applications/<name>/` directory and its own schema namespace |
| Shared package change | Touches `packages/` (`04-Folder-Structure.md`, Section 6) |
| Documentation-only change | Touches only `docs/` |
| Infrastructure change | Touches only `infra/` |

This classification determines which review path a change follows (Section 6).

### 3.2 Design Proposal Requirement

A Core change or a new subsystem addition (`04-Folder-Structure.md`, Section 12) requires a written design proposal before implementation begins, covering:

- Which subsystem(s) are affected and why
- How the change respects the dependency rules in `02-System-Architecture.md`, Section 6
- Whether any document in the `docs/` set (`00`–`15`) needs a corresponding update
- Test strategy per `11-Coding-Standards.md`, Section 6

An Application-only change does not require this level of upfront proposal, since it cannot, by construction, affect Core's contracts or other Applications.

## 4. Design Review

### 4.1 Who Reviews

Design proposals for Core changes (Section 3.2) are reviewed by maintainers with standing responsibility for the affected subsystem (`04-Folder-Structure.md`, Section 4, ownership boundary). Application changes are reviewed by that Application's own team, per the ownership model in `04-Folder-Structure.md`, Section 5.

### 4.2 What Is Reviewed

Design review checks the proposal against:

- The Separation Principle (`00-GENESIS_CONTEXT.md`, Section 5) — does this keep application-specific logic out of Core?
- The dependency rules (`02-System-Architecture.md`, Section 6)
- Whether the change is additive/backward-compatible or requires a version bump (`10-API-Standards.md`, Section 3; `08-Plugin-System.md`, Section 5.3)

A design proposal that fails any of these checks is revised before implementation begins, not after a pull request is already open.

## 5. Implementation

### 5.1 Branching

Work happens on a feature branch, named `<classification>/<short-description>` (e.g., `core/memory-similarity-retrieval`, `app/product-manager-sprint-view`), making a branch's blast radius visible before its contents are reviewed.

### 5.2 Commit Conventions

Commits follow a structured, machine-parseable format:

```
<type>(<scope>): <short summary>

<body: what changed and why, referencing the relevant design proposal or
docs/ section if applicable>
```

| `type` | Meaning |
|---|---|
| `feat` | New capability |
| `fix` | Defect correction |
| `refactor` | No behavior change |
| `docs` | Documentation-only change |
| `test` | Test-only change |
| `chore` | Tooling, dependency, or config change |

`<scope>` matches the subsystem or Application name (e.g., `runtime`, `memory`, `product-manager`), consistent with the naming conventions in `04-Folder-Structure.md`, Section 9.

### 5.3 Incremental, Reviewable Commits

Commits are structured so that architectural changes (e.g., a new contract) are separated from routine implementation detail, allowing a reviewer to evaluate architectural impact (Section 7) without wading through unrelated changes in the same diff.

## 6. Testing

### 6.1 Required Before Opening a Pull Request

Per `11-Coding-Standards.md`, Section 6.2, the appropriate test types for the change's classification (Section 3.1) are written and passing locally before a pull request is opened:

| Classification | Minimum Required Tests |
|---|---|
| Core change | Unit + integration for the affected subsystem; contract tests if a public contract changed |
| Application change | Unit tests for new Application logic; e2e tests if the change affects a user-facing flow |
| Shared package change | Unit tests, plus confirmation that dependent Core/Application tests still pass |
| Infrastructure change | Deployment validation in a staging environment before merge |

### 6.2 Lifecycle-Sensitive Changes

Any change touching Runtime lifecycle transitions (`06-Agent-Runtime.md`, Section 4.1) or Approval Gateway logic (`05-Agent-OS.md`, Section 6) includes the invariant tests required by `11-Coding-Standards.md`, Section 6.4, as a hard prerequisite for review — not something added after reviewer feedback.

## 7. Pull Requests

### 7.1 Pull Request Contents

A pull request description states:

- The classification (Section 3.1)
- A link to the design proposal, if one was required (Section 3.2)
- Which `docs/` files, if any, are updated in this change
- A summary of the test coverage added (Section 6)

### 7.2 Automated Checks (CI)

Before any human review, CI enforces:

- Formatting and static type checks (`11-Coding-Standards.md`, Sections 3.1, 4.1)
- Import-linting for the dependency rules in `11-Coding-Standards.md`, Section 2
- Full test suite for the affected classification (Section 6.1)
- OpenAPI schema diff check: any change to a Core API contract is flagged for explicit versioning review (`10-API-Standards.md`, Section 3)

A pull request that fails any automated check does not proceed to human review.

### 7.3 Required Reviewers

| Classification | Required Reviewer(s) |
|---|---|
| Core change | At least one maintainer of each affected subsystem |
| Application change | At least one member of that Application's team |
| Shared package change | At least one maintainer from Core and one from an Application team using the package |
| Documentation-only change | At least one maintainer familiar with the affected document's subject area |

## 8. Architectural Review

### 8.1 When It Applies

Architectural review is a distinct, mandatory step for any Core change or new subsystem addition (Section 3.1), performed in addition to (not instead of) the standard code review in Section 7.3.

### 8.2 What It Checks

Architectural review re-verifies, at the point of finished implementation (not just the earlier design proposal), the checklist from `11-Coding-Standards.md`, Section 7.1, item 1 — architectural compliance — treating any violation as blocking regardless of test coverage or code quality.

### 8.3 Escalation

Disagreement about whether a change is architecturally compliant is resolved per `11-Coding-Standards.md`, Section 7.3: by reference to the specific document and section defining the rule in question, with a documentation update proposed first if the existing documents do not address the situation.

## 9. Human-Approval Gate for Core Changes

In addition to reviewer approval (Section 7.3) and architectural review (Section 8), a Core change requires an explicit, recorded approval from a maintainer with standing authority over Genesis Core as a whole before merge — distinct from subsystem-specific reviewer approval. This mirrors, at the level of the engineering process itself, the same human-oversight principle Genesis enforces for agent actions (`05-Agent-OS.md`, Section 6): a consequential, hard-to-reverse change to shared infrastructure does not proceed on implicit consensus alone.

## 10. Documentation Updates

### 10.1 Same-Change Requirement

Per `10-API-Standards.md`, Section 8.3, and `11-Coding-Standards.md`, Section 7.1, item 4, any change affecting the meaning of a `docs/` file (`00`–`15`) includes the corresponding documentation update in the same pull request — not a follow-up. This is checked explicitly during both code review (Section 7.3) and architectural review (Section 8) where applicable.

### 10.2 Documentation-Only Changes

A documentation-only change still follows the review path in Section 7.3 (a subject-matter-familiar reviewer), since the `docs/` set is treated as authoritative and load-bearing for future architectural decisions (`04-Folder-Structure.md`, Section 13; `09-Database-Design.md`, Section 9) — not as informal notes.

## 11. Merge and Release

### 11.1 Merge Criteria

A pull request merges only once:

- All automated checks (Section 7.2) pass.
- All required reviewers (Section 7.3) have approved.
- Architectural review (Section 8), if applicable, has passed.
- The human-approval gate (Section 9), if applicable, has been recorded.

### 11.2 Release Cadence

Core and each Application may release on independent cadences, consistent with the monorepo rationale in `04-Folder-Structure.md`, Section 2 — a Core release does not require every Application to release simultaneously, provided backward compatibility (`10-API-Standards.md`, Section 3.2) holds.

### 11.3 Rollback

Because migrations favor reversibility (`09-Database-Design.md`, Section 5.2) and API changes favor backward compatibility, a release can typically be rolled back independently of data migration; any migration explicitly marked irreversible (per the same section) is called out in the release notes as a rollback constraint.

## 12. Relationship to Other Documents

This document defines the process. It intentionally does not redefine:

- The architectural rules being enforced → see `02-System-Architecture.md`, `04-Folder-Structure.md`
- The code-level conventions checked in CI and review → see `11-Coding-Standards.md`
- The API versioning rules checked during the OpenAPI schema diff (Section 7.2) → see `10-API-Standards.md`, Section 3
- The migration principles checked during Core changes touching persistence → see `09-Database-Design.md`, Section 5

Where this document and any process actually followed in practice diverge, this document is treated as authoritative until formally revised — the workflow itself is expected to evolve deliberately, not silently.