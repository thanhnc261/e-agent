# ADR 0013: integration auth SDK, tenant app registrations and user-delegated connections

Date: 2026-10-06. Status: Proposed. Refines ADR 0012.

## Context

ADR 0012 made integration management schema-driven but assumed connections owned by the tenant. The product needs two levels:

- tenant admins enable an integration and supply tenant-level configuration, such as a Google OAuth client ID and secret;
- users connect their own accounts (an Odoo API key, Google OAuth), so the agent acts with each user's provider permissions.

Every provider needs the same mechanics: storage, refresh, revocation, scope checks and audit. Reimplementing them per adapter would be slow and unsafe. Agent-auth products (Auth0 Token Vault, Arcade just-in-time auth, Nango) converge on the same pattern: the host vaults tokens, the agent receives only short-lived access, and connection happens at the moment it is needed. Odoo 19 JSON-2 accepts only API keys, not passwords. Google issues partial grants under granular consent and 7-day refresh tokens for apps in "Testing" status.

Details are in [integration auth SDK](../integration-auth-sdk.md).

## Decision

1. Add an `auth` module to the public plugin SDK with:
   - manifest-declared auth methods (`api_key`, `basic`, `bearer_static`, `oauth2_authorization_code`, `oauth2_client_credentials`, `service_account_jwt`, `workload_identity`, `mtls`, `custom`);
   - a runtime `AuthContext` (auth-applied HTTP client, scope checks, refresh-once-on-401);
   - typed auth errors;
   - an `AuthScheme` extension protocol;
   - a conformance kit.
   Provider adapters never implement storage, OAuth flows or refresh.
2. Host services (`SecretStore`, `CredentialService` with single-flight refresh, `OAuthEngine`, `ConnectionResolver`, `IdentityProbe`) live in the server/kernel or in their own adapters.
3. Connections have `ownership: tenant_shared | user_delegated`. A user connection is usable only for runs requested by its owner. Admins can revoke but not read or use it.
4. Tenant policy per integration sets which auth methods are allowed, whether user connections are allowed, allowed scopes, an optional domain restriction, and the credential mode per capability (`user_delegated_required`, `tenant_shared_only`, `user_preferred` with read-only fallback).
5. The credential subject is the requester's or the tenant's connection, never the approver's. It is included in the approval digest together with connection version. A credential change makes the approval stale.
6. A missing connection or missing scope pauses the run (`WAITING_INPUT` / `connect_required`). Only a user gesture starts a connect flow.
7. The Odoo adapter uses per-user (or integration-user) **API keys**. `basic` exists in the SDK for other providers.
8. MVP: SDK module with `api_key` and `service_account_jwt`, tenant-shared connections, local `SecretStore` and the credential subject in contracts. Phase 2: user-delegated connections, OAuth engine, app registrations, admin *Integrations* page, user *My integrations* page and the Google Workspace adapter.

## Alternatives considered

- **Each adapter handles its own auth.** Duplicated, inconsistent security; secrets leak into adapter-specific storage.
- **Managed agent-auth service (Auth0 Token Vault, Arcade, Nango) as the core.** Fast coverage, but it adds external dependency, license and data-residency questions. Any of them can sit behind `CredentialService`/`OAuthEngine` later without changing adapters.
- **Shared service accounts only.** Simpler, but the agent would exceed the requester's own provider permissions and break per-user accountability.
- **Execute with the approver's credential.** It confuses who authored the action and creates a confused-deputy risk.

## Consequences

- Contracts gain `ownership`, `owner_principal`, `credential_subject` and `connection_version`.
- Adapters must ship auth declarations, identity probes and run the auth conformance kit.
- Users must manage their own connections. Re-authentication prompts become part of the UX.

## Verification

- Conformance kit passes for every declared auth method of every adapter.
- A user connection cannot be used for another user's run (negative test).
- A credential change between approval and dispatch makes the approval stale.
- A partial Google grant leads to `ScopeMissing` and an incremental consent request; `invalid_grant` leads to `reauth_required`.
- Concurrent runs refreshing one rotating token perform exactly one refresh.
- Canary-secret scan is clean.
- Revisit if a managed agent-auth service is adopted, or when token exchange (RFC 8693) or identity-provider federation replaces stored user credentials.
