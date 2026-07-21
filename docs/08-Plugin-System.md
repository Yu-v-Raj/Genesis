# Genesis — Plugin System

## 1. Purpose

This document defines the Plugin System: the Agent OS subsystem responsible for allowing new capabilities — tools, integrations, extensions — to be added to Genesis without modifying Core. It operationalizes the Composition Over Inheritance and Extensibility principles established in `00-GENESIS_CONTEXT.md` (Section 8) and `02-System-Architecture.md` (Section 8.3).

This document is application-agnostic. The Plugin System knows how to discover, load, sandbox, and register a plugin; it has no concept of what any given plugin does.

## 2. Role of the Plugin System Within the Agent OS

The Plugin System is the mechanism through which Genesis grows capability over time without growing Core. Where the Tool Manager (`02-System-Architecture.md`, Section 5.2) mediates an agent's *invocation* of a tool at runtime, the Plugin System is responsible for everything upstream of that: discovering that a tool exists, verifying it is safe to load, registering it, and managing its lifecycle independent of any single agent execution.

```
Plugin Author  ──writes──▶  Plugin Package
                                  │
                                  ▼
                          Plugin System (discover, validate, register, sandbox)
                                  │
                                  ▼
                          Tool Manager (mediates invocation at runtime)
                                  │
                                  ▼
                          Agent (invokes via Runtime, see 06-Agent-Runtime.md)
```

## 3. Plugin Architecture

### 3.1 Plugin Package Structure

A plugin is a self-contained package declaring, at minimum:

| Element | Purpose |
|---|---|
| Manifest | Declarative metadata: name, version, capability type, declared permissions, dependencies |
| Interface implementation | Code implementing the Plugin System's published extension contract |
| Sandboxing declarations | Explicit statement of what external resources (network, filesystem, specific tool APIs) the plugin requires |

### 3.2 Manifest Schema (Conceptual)

```
plugin:
  name: string
  version: semver
  capability_type: tool | data_source | communication_adapter | memory_backend
  permissions:
    network: [allowed_hosts]
    filesystem: read | none
    tools: [external_apis_invoked]
  dependencies:
    - name: string
      version: semver_range
  entrypoint: module_path
```

The manifest is the unit of trust evaluation (Section 6) and the unit of dependency resolution (Section 5) — nothing about a plugin is trusted or loaded based on its code alone, without a corresponding manifest declaration.

### 3.3 Capability Types

| Capability Type | Description |
|---|---|
| Tool | An action an agent can invoke through the Tool Manager (e.g., calling an external API) |
| Data Source | A read-only integration exposing external data to the Memory System or an agent |
| Communication Adapter | An alternative transport implementation behind the Communication Layer's port (`02-System-Architecture.md`, Section 5.2) |
| Memory Backend | An alternative persistence adapter behind the Memory System's port (`07-Memory-System.md`, Section 5) |

Each capability type maps to a specific Core subsystem's extension point, consistent with the extensibility mechanisms defined in `02-System-Architecture.md`, Section 10.

## 4. Plugin Lifecycle

```
┌───────────┐   discover   ┌────────────┐   validate   ┌────────────┐
│ Discovered │─────────────▶│  Validated  │─────────────▶│ Registered │
└───────────┘              └────────────┘              └─────┬──────┘
                                                                │
                                                    load/activate
                                                                ▼
                                                          ┌───────────┐
                                                          │  Active    │
                                                          └─────┬─────┘
                                                                │
                                                   deactivate / error
                                                                ▼
                                                          ┌───────────┐
                                                          │ Disabled /  │
                                                          │ Quarantined │
                                                          └───────────┘
```

| State | Meaning |
|---|---|
| Discovered | The Plugin System has located a candidate plugin package (Section 5) but has not yet inspected its manifest |
| Validated | The manifest has been parsed, its declared permissions and dependencies checked against policy (Section 6) |
| Registered | The plugin's capability has been recorded and made available to the relevant Core subsystem (Tool Manager, Memory System, etc.) |
| Active | The plugin is loaded and available for invocation |
| Disabled / Quarantined | The plugin has been deliberately deactivated, or automatically quarantined following a runtime violation (Section 6.3) |

A plugin's lifecycle is tracked independently of any single agent execution's lifecycle (`06-Agent-Runtime.md`, Section 4) — a plugin remains Active across many executions until explicitly disabled.

## 5. Discovery and Registration

### 5.1 Discovery

The Plugin System discovers candidate plugins from a configured set of sources:

- A local plugin directory (for first-party and development plugins)
- A versioned plugin registry (future ecosystem support, Section 8)

Discovery only produces candidates; it never registers a plugin automatically without passing through validation (Section 5.2).

### 5.2 Validation and Registration

Validation checks, in order:

1. **Manifest well-formedness** — the manifest parses and declares all required fields (Section 3.2).
2. **Permission policy compliance** — declared permissions (network hosts, filesystem access, invoked external APIs) are checked against an operator-configured allowlist. A plugin declaring permissions outside policy is rejected before registration, not merely flagged.
3. **Dependency resolution** — declared dependencies (Section 6... see Section 5.3) are resolved and checked for conflicts.

Only a plugin that passes all three checks is Registered and made available to its corresponding Core subsystem's extension point (Section 3.3).

### 5.3 Dependency Management

Plugins may declare dependencies on:

- Other plugins (by name and version range)
- A minimum Genesis Core contract version (e.g., a minimum `tool_contract` version)

The Plugin System resolves these declarations at validation time and refuses registration if:

- A required dependency is not present among Registered or Active plugins.
- A version conflict exists between two plugins' declared dependency ranges.

This mirrors, at the plugin level, the same contract-first discipline used between Applications and Core (`02-System-Architecture.md`, Section 8.1): a plugin depends on declared versions of other plugins' or Core's contracts, never on their internal implementation.

## 6. Security Considerations

### 6.1 Sandboxing

Every Active plugin executes within a sandbox boundary that enforces its manifest-declared permissions (Section 3.2) at runtime, not merely at validation time. A plugin cannot access a network host, filesystem path, or external API it did not declare, regardless of what its code attempts.

### 6.2 Least Privilege by Default

The Plugin System's default permission set for any newly discovered plugin is empty. A plugin gains only the capabilities it explicitly declares and that pass policy validation (Section 5.2) — there is no implicit or inherited access to Core internals, other plugins' data, or Applications' data.

### 6.3 Runtime Violation Handling

If an Active plugin attempts an action outside its declared and validated permissions, the Plugin System:

1. Blocks the attempted action at the sandbox boundary.
2. Transitions the plugin to Quarantined (Section 4).
3. Logs the violation through Core Services (`02-System-Architecture.md`, Section 9, Observability) for review.

A quarantined plugin is not automatically reinstated; it requires explicit operator review and re-registration.

### 6.4 No Plugin-to-Core-Internals Access

Consistent with the dependency rules in `02-System-Architecture.md`, Section 6 ("Plugins may depend on the Tool Manager and Plugin System contracts. Plugins may never depend on Runtime or Workflow Engine internals directly"), a plugin's sandbox has no path to Runtime or Workflow Engine internals — only to the specific extension point corresponding to its declared capability type (Section 3.3).

## 7. Extension Mechanisms

The Plugin System is itself the primary extension mechanism for the rest of the Agent OS. Concretely, it allows the following to be added without modifying Core:

| Extension | How the Plugin System Enables It |
|---|---|
| New external tool integrations | Registered as a Tool capability type, invoked later through the Tool Manager |
| New data integrations | Registered as a Data Source capability type |
| New message transports | Registered as a Communication Adapter, implementing the Communication Layer's existing port |
| New persistence backends | Registered as a Memory Backend, implementing the Memory System's existing port |

This directly realizes the extensibility axes described in `02-System-Architecture.md`, Section 10 — new tools/integrations and new memory backends are explicitly listed there as growth areas addressed through the Plugin System.

## 8. Future Plugin Ecosystem Support

The current Plugin System supports local, first-party-managed plugin discovery (Section 5.1). Planned ecosystem-level support, designed to be additive rather than requiring rework of the mechanisms above:

| Future Capability | Design Intent |
|---|---|
| Versioned plugin registry | A remote, queryable source of discoverable plugins, layered on top of the existing discovery mechanism (Section 5.1) rather than replacing it |
| Third-party plugin publishing | Requires a signing/provenance mechanism added to the manifest schema (Section 3.2), so validation (Section 5.2) can verify plugin origin before registration |
| Plugin marketplace / directory UI | An Application-layer concern (a UI built against Plugin System contracts), not a Core capability itself — consistent with the Separation Principle |
| Automated compatibility testing | Extending dependency resolution (Section 5.3) to run declared compatibility checks against a target Core contract version before registration is offered to an operator |

Each of these is designed to extend Sections 5 and 6 rather than to change how Registered/Active plugins are sandboxed or invoked — preserving the security guarantees in Section 6 regardless of how large the plugin ecosystem grows.

## 9. Relationship to Other Documents

This document defines the Plugin System's architecture, lifecycle, and security model. It intentionally does not define:

- How the Tool Manager mediates invocation of a registered tool at runtime → see `06-Agent-Runtime.md`
- How a Memory Backend plugin's data is structured once registered → see `07-Memory-System.md`
- API-level endpoints for plugin registration/management → see `10-API-Standards.md`

Where a future document appears to describe plugin behavior inconsistent with the security model in Section 6, this document takes precedence until formally revised.