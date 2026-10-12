# ADR 0017: Member-readable discovery read models

Date: 2026-10-09. Status: **Accepted** (implementation decision for the enterprise overlay adoption plan, work package API-01).

## Context

The [enterprise overlay adoption plan](../plans/2026-10-08-enterprise-overlay-adoption.md) §3 needs two things the API does not have: a requester-visible list of the task types this workspace can actually run, and a member-safe view of the connections those tasks would use. Without them a UI can only hard-code a workflow menu or render fixture connections, which claims capabilities the product does not have.

The existing API is run-scoped. `PluginRegistry` already holds admitted capabilities, their bindings and their input schemas; `ConnectionCatalog` already answers "is this connection usable by this requester in this tenant" for execution (ADR 0012, ADR 0013). The [Phase 2 auth API design](../integration-auth-sdk.md) anticipates a member-readable `GET /v1/me/connections` separate from administrative endpoints.

Administrative connection management, delegated OAuth, provider health probing and a durable cross-session work inbox are out of scope here and remain unimplemented.

## Decision

Add one application service, `e_agent.kernel.discovery`, and two authenticated read-only endpoints that use it:

- `GET /v1/me/connections` — connections the calling principal may actually use.
- `GET /v1/me/task-catalog` — admitted task templates the calling principal may actually start.

Both are projections assembled from already-admitted metadata. Specifically:

1. **Authorization reuses execution authority.** A connection appears only when `ConnectionCatalog.usable` accepts it for this principal's tenant, resource scope and ownership. A connection in another tenant, outside scope, or delegated to someone else is absent, with no marker explaining that something was withheld. Absence and non-existence are indistinguishable, matching the existing `FORBIDDEN → 404` rule.
2. **No secrets, no admin fields.** The response carries no `secret_ref`, no credential material and no settings. The acting identity is disclosed only as the provider subject the connection already publishes in approval presentations, and is `null` when the connection does not publish one.
3. **Configuration status and observed health are separate facts.** `configuration_status` is the recorded `ConnectionStatus`. `observed_health` is always `"unknown"`: neither endpoint performs a provider probe as a side effect of rendering, so no response may imply a successful health check.
4. **No icons or manifest URLs.** Icon delivery needs a host-controlled policy that does not exist; returning a URL would make the browser fetch arbitrary hosts. Until that policy exists the responses carry identifiers and text only.
5. **A template is not a credential selector.** A catalog entry names a capability contract and its availability. The server still resolves bindings and connections and authorizes every action again at execution; nothing in the catalog lets a model or a browser choose a connection or an identity.
6. **Availability is decided by the host's own rules.** A capability is `available` only when the checks execution itself performs succeed: exactly one usable in-scope connection, `PluginRegistry.resolve` accepting that contract and connection, and a unique executor for the resulting binding. An answer additionally needs exactly one usable read connection across all bindings and an unambiguous registered verifier, because it is produced and recomputed through that read path and fails without one. Otherwise the entry is `unavailable` with a bounded machine-readable reason (`no_usable_connection`, `ambiguous_binding`, `no_executor`, `no_verifier`). Counting distinct connection ids is explicitly not sufficient: duplicate bindings on one connection are a conflict `resolve` refuses, and that refusal must be reported rather than hidden. Unknown is never rendered as available, and no execution rule may be relaxed to make a catalog claim true.
7. **Versioned and timestamped.** Both responses carry `schema_version: "1"` and the `observed_at` time at which the projection was assembled, so a client can show freshness and can reject a version it does not understand.

Generated OpenAPI and the TypeScript client are regenerated from the implementation; the UI consumes the generated wire types through a bounded runtime projection, never a hand-maintained second schema.

## Alternatives considered

- **Reuse an administrative connection endpoint.** Rejected: an admin DTO carries configuration and secret references, and reusing it would leak administrative detail to ordinary members.
- **Return every tenant connection with an `authorized: false` flag.** Rejected: that discloses the existence of connections the requester may not see, contradicting the existing cross-scope indistinguishability rule.
- **Probe providers so the catalog can show live health.** Rejected: rendering a page must not cause provider traffic or be mistaken for verification. Health belongs to an authorized operation, not to a read model.
- **Serve manifest icon URLs.** Rejected without a host-controlled asset policy.
- **Let the catalog carry binding or connection identifiers for the client to submit.** Rejected: the host resolves bindings, and an action is authorized again at execution.

## Consequences

The UI can show real installed scope and a member-safe connection inventory instead of a hard-coded menu or fixture data. Two endpoints and one kernel module are added; no existing endpoint, event or approval path changes. Clients must handle `available`/`unavailable`, unknown health and an empty result, and must treat an unrecognised `schema_version` as unsupported rather than rendering it.

These endpoints do not implement integration management: there is still no way to connect, re-authorize, disable or repair a connection through the API, and the UI must not present one. Durable cross-session work listing, proposal editing and delegated OAuth remain out of scope. Live-release readiness is unchanged by this ADR.

## Verification

Server tests cover tenant and principal filtering, out-of-scope and delegated-to-another-user connections being absent, the absence of secret fields in every response, health always unknown, availability and each of its reasons, agreement between the catalog and `PluginRegistry.resolve` for duplicate bindings, answer verifier and read-path requirements, and the `schema_version`/`observed_at` envelope. Client tests cover malformed envelopes and per-field malformed entries, kept distinct from a legitimate empty list and from denied. `scripts/export_openapi.py --check` and the UI's `gen:check` keep the generated client in step. Browser conformance covers the member views rendering loading, empty, denied and unknown states without inventing a connect action. Revisit when administrative integration management or delegated OAuth lands.
