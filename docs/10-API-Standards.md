# Genesis — API Standards

## 1. Purpose

This document defines the conventions governing every API surface in Genesis — Core's public contracts and each Application's own endpoints. It operationalizes the Contracts Before Implementations principle (`02-System-Architecture.md`, Section 8.1) at the concrete level of HTTP request/response design, versioning, error shape, and authentication.

Every API exposed by Core or by an Application is expected to conform to this document. Deviations require explicit justification recorded alongside the API definition, not silent inconsistency.

## 2. API Design Philosophy

### 2.1 Contract-First

Every endpoint is defined by its schema before it is implemented. FastAPI's Pydantic-based request/response models (`03-Tech-Stack.md`, Section 4.1) are the source of truth for a contract's shape; the generated OpenAPI schema is a derived artifact, not a hand-maintained one.

### 2.2 The API Is the Boundary

Per the dependency rules in `02-System-Architecture.md`, Section 6, Applications interact with Core exclusively through Core's API contracts (`core/contracts/` and `core/api/`, see `04-Folder-Structure.md`, Section 4). The API is not one of several ways to access Core — for any consumer outside Core's own codebase, it is the *only* way.

### 2.3 Explicit Over Implicit

Request and response shapes state exactly what they mean: fields are typed, required-vs-optional is explicit, and enums are used in place of loosely-typed strings wherever a fixed set of values applies (e.g., lifecycle states from `06-Agent-Runtime.md`, Section 4.1). Nothing about an API's behavior should require reading its implementation to understand.

### 2.4 Stability Over Convenience

An endpoint's shape, once published at a given version (Section 3), is not changed in a breaking way. Convenience refactors that would break existing consumers are deferred to the next version rather than applied in place.

## 3. Versioning

### 3.1 Versioning Scheme

Genesis APIs are versioned at the URL path level:

```
/api/v1/...
/api/v2/...
```

A major version increment is required for any breaking change: removing a field, changing a field's type or meaning, changing an endpoint's URL or HTTP method, or changing error-shape semantics (Section 5).

### 3.2 Backward Compatibility Within a Version

Within a given major version, only additive, non-breaking changes are permitted:

- Adding a new optional request field
- Adding a new response field
- Adding a new endpoint

Consumers built against `v1` must continue to function without modification for the entire supported lifetime of `v1`, even as additive changes are introduced.

### 3.3 Deprecation

A version is not removed while any Application still depends on it in production. Deprecation is announced (via changelog and, where feasible, a response header on the deprecated version's endpoints) with a defined support window before removal, tracked in `13-Roadmap.md`.

## 4. Request/Response Standards

### 4.1 Structure

Every request and response body is a JSON object (never a bare array or scalar at the top level), so that fields can be added later without breaking existing consumers.

```
// Request
{
  "data": { ... }
}

// Response (success)
{
  "data": { ... },
  "meta": {
    "request_id": "string"
  }
}
```

### 4.2 Pagination

List-returning endpoints use cursor-based pagination, not offset-based, since offset-based pagination is unstable under concurrent writes to append-heavy tables (see `09-Database-Design.md`, Section 6):

```
{
  "data": [ ... ],
  "meta": {
    "request_id": "string",
    "next_cursor": "string | null"
  }
}
```

### 4.3 Field Naming

All JSON field names use `snake_case`, matching Python/Pydantic conventions on the backend and translated to the frontend's TypeScript types via generated types (see `03-Tech-Stack.md`, Section 3.3) rather than hand-maintained duplicate models.

### 4.4 Timestamps and Identifiers

- All timestamps are ISO 8601, UTC, with explicit `Z` suffix.
- All identifiers (`execution_id`, `record_id`, `plugin_id`, etc.) are opaque strings (UUIDs). Consumers must never parse or infer structure from an identifier's contents.

### 4.5 Enums Over Free Text

Any field representing a fixed set of states (e.g., an execution's lifecycle state from `06-Agent-Runtime.md`, Section 4.1) is transmitted as a defined enum value, documented in the endpoint's schema, never as unconstrained free text.

## 5. Error Handling

### 5.1 Error Response Shape

All error responses share one consistent shape, regardless of which endpoint or Application produced them:

```
{
  "error": {
    "code": "string",       // stable, machine-readable identifier
    "message": "string",    // human-readable description
    "details": { ... }      // optional, structured context
  },
  "meta": {
    "request_id": "string"
  }
}
```

### 5.2 HTTP Status Code Usage

| Status | Meaning |
|---|---|
| 400 | Request failed validation (malformed input, schema violation) |
| 401 | Missing or invalid authentication credentials |
| 403 | Authenticated, but not authorized for the requested action |
| 404 | Referenced resource does not exist (or is not visible to the caller, per ownership boundaries in `09-Database-Design.md`, Section 3.2) |
| 409 | Request conflicts with current resource state (e.g., an invalid lifecycle transition per `06-Agent-Runtime.md`, Section 4.1) |
| 422 | Request is well-formed but semantically invalid (e.g., references a nonexistent workflow node) |
| 429 | Caller has exceeded a rate or capacity limit (e.g., Runtime Scheduler capacity, `06-Agent-Runtime.md`, Section 5.1) |
| 500 | Unexpected internal error; always logged with a `request_id` for later correlation |

### 5.3 Error Code Stability

The `error.code` field is a stable, versioned identifier (e.g., `execution_not_found`, `invalid_lifecycle_transition`, `approval_required`) that consumers may branch on programmatically. `error.message` is intended for human display and may be reworded without a version bump; `error.code` may not.

### 5.4 No Silent Failure

Consistent with the Fail Safe, Not Fail Silent principle (`02-System-Architecture.md`, Section 8.4), an API never returns a 200-level response representing a failed operation with the failure only described in a body field — failures are always reflected in the HTTP status code and the error shape above.

## 6. Authentication

### 6.1 Mechanism

All authenticated endpoints require a JWT bearer token (see `03-Tech-Stack.md`, Section 7.1), passed via the `Authorization: Bearer <token>` header. No endpoint accepts credentials via query parameters.

### 6.2 Token Lifetime

Access tokens are short-lived; refresh tokens are used to obtain new access tokens without re-authenticating, mitigating the revocation weakness noted in `03-Tech-Stack.md`, Section 7.1.

### 6.3 Authorization Scope

Authentication establishes *who* is calling; authorization (enforced by Core Services, `02-System-Architecture.md`, Section 5.2) establishes *what* they may do, including the `application_id`-scoped visibility rules defined in `09-Database-Design.md`, Section 3.2. An authenticated caller from one Application's context is never authorized to act on another Application's resources.

### 6.4 Human Approval Endpoints

Endpoints related to the Approval Gateway (`05-Agent-OS.md`, Section 6) additionally require the caller to hold a reviewer-authorized identity, distinct from the identity used to submit the original task — a task submitter cannot approve their own submission through the same credential.

## 7. Naming Conventions

| Element | Convention | Example |
|---|---|---|
| URL paths | `kebab-case`, plural nouns for collections | `/api/v1/agent-executions` |
| Path parameters | `snake_case`, explicit resource name | `/api/v1/agent-executions/{execution_id}` |
| Query parameters | `snake_case` | `?application_id=...&cursor=...` |
| JSON fields | `snake_case` | `owner_execution_id` |
| Enum values | `SCREAMING_SNAKE_CASE` | `AWAITING_APPROVAL` |
| Error codes | `snake_case` | `invalid_lifecycle_transition` |

Endpoint naming mirrors the entity boundaries defined in `09-Database-Design.md`, Section 4 — a resource's API path indicates which subsystem owns it, the same way its table's schema prefix does.

## 8. Documentation Requirements

### 8.1 Schema-Derived Documentation

Every endpoint's documentation is derived from its Pydantic schema and FastAPI route definition (OpenAPI generation, `03-Tech-Stack.md`, Section 4.1) — not maintained as a separate hand-written document that can drift from the implementation.

### 8.2 Required Annotations

Every endpoint definition must include:

- A human-readable summary and description.
- Explicit documentation of every possible error response (Section 5), not just the success case.
- An example request and response payload.
- The minimum required authorization scope (Section 6.3).

### 8.3 Contract Changes Require Documentation Updates in the Same Change

A pull request modifying a request/response schema must update its endpoint's documentation annotations in the same commit — schema and documentation are not permitted to diverge, even temporarily, per the review process defined in `12-Development-Workflow.md`.

## 9. Relationship to Other Documents

This document defines API-level conventions. It intentionally does not define:

- Why FastAPI/JWT were chosen → see `03-Tech-Stack.md`, Sections 4.1 and 7.1
- The underlying lifecycle states referenced by execution-related endpoints → see `06-Agent-Runtime.md`, Section 4.1
- The database entities these endpoints ultimately read/write → see `09-Database-Design.md`
- The review and CI process enforcing these standards → see `12-Development-Workflow.md`

Where a future endpoint definition appears to conflict with the standards in this document, this document takes precedence until formally revised.