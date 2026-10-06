# ADR 0012: schema-driven integration, connection and credential management

Date: 2026-10-06. Status: Accepted (project owner, decisions D1–D5, 2026-10-06). Extends HLD §5 and ADR 0011.

## Context

e-agent must integrate many enterprise systems quickly (Odoo, CRMs, Google Workspace, BigQuery, MCP servers) and absorb technology changes without rewriting the UI or kernel. Administrators will need pages to manage connections, credentials, auth and scopes. If those pages or the kernel contain provider-specific code, every new integration becomes a UI and kernel release, and secrets risk leaking into places the model or UI can reach. The current design has connections with secret references set by operator profiles, but no admin model.

Established platforms solve this with schemas: Airbyte connection specs in JSON Schema with secret annotations and declarative OAuth, n8n credential types, JSON Forms renderers. RFC 9700 and the MCP authorization spec define current OAuth practice. Details are in [integration management](../integration-management.md) §2.

## Decision

1. Each adapter manifest declares, in a provider-neutral form: its connection settings schema (JSON Schema 2020-12, with secret fields marked write-only), optional UI hints, auth methods, OAuth parameters, resource-scope schema, `test_connection` and provided bindings. Display text and icons are packaged assets.
2. Admin UI and admin API are **generic**. They render and validate from manifests, and contain no provider identifiers; a CI denylist gate enforces this under `ui/`.
3. Credentials live behind a `SecretStore` port: `local-encrypted` in MVP; OpenBao/Vault/cloud secret managers later. Secrets are write-only through the API and resolved as a short-lived handle only inside the adapter at dispatch.
4. One generic server-side OAuth engine, driven by manifests, follows RFC 9700 (authorization code + PKCE, `state`, exact redirect URIs, refresh rotation, revocation).
5. Connections are versioned. The approval digest includes the connection version, so configuration changes make pending approvals stale.
6. A new `integration_admin` role is separate from requester and approver, with step-up re-authentication for changes. Admin APIs are never exposed as agent tools.
7. Admin pages configure **admitted** integrations only. Adding adapter code remains a deployment action with artifact admission.
8. Phase 2 includes the admin pages (confirmed by the project owner). Auth mechanics, tenant app registrations and user-delegated connections are specified in [ADR 0013](0013-integration-auth-sdk-and-delegated-connections.md). MVP scope: manifest schemas, the `SecretStore` port with the local adapter, connection versioning and `test_connection`. Admin pages, the OAuth engine and the MCP integration type are Phase 2.

## Alternatives considered

- **Per-provider admin screens.** Fast for the first integration, but they couple the UI to vendors and slow every later one.
- **Secrets in profiles or environment only.** Fine for a single developer, but there is no rotation, audit or tenant scoping.
- **Adopt a managed integration-auth platform (e.g. Nango) as the core.** It covers many APIs, but it is a license and dependency decision. It stays a possible adapter behind the credential/OAuth port.
- **Allow uploading connector code or config-only HTTP connectors from the UI.** Rejected for now: it bypasses artifact admission and turns admin into a code-execution path.

## Consequences

- Each adapter ships schemas, i18n and a `test_connection`. These are small additions to its manifest and conformance tests.
- A schema-form renderer becomes part of the default component layer.
- The approval digest input gains `connection_version` (ADR 0006 profile unchanged).

## Verification

- Unknown fixture integration configurable end to end with no UI change.
- Canary-secret scan finds no secret value in responses, events, logs, traces or evidence.
- Connection change makes a pending approval stale; a disabled connection blocks invocation before any provider call.
- OAuth negative tests (state, redirect, PKCE).
- Provider denylist gate on `ui/`.
- Revisit when a managed integration-auth service or a standard connector-spec format offers material benefit, or when tenants require bring-your-own-key.
