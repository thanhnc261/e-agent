# ADR 0005: Odoo 19 JSON-2 transport and transactional bridge commands

Date: 2026-10-06. Status: Proposed. Refines ADR 0001 (bridge addon permitted).

## Context

- Odoo 19 introduces the External JSON-2 API: `POST /json/2/<model>/<method>`, authenticated by `Authorization: Bearer <API key>`, with `X-Odoo-Database` where needed. **Each call runs in its own SQL transaction**, and real HTTP status codes are returned.
- `/xmlrpc`, `/xmlrpc/2` and `/jsonrpc` are deprecated in Odoo 19. Removal is staged: the `db` service in Odoo 20, `common`/`object` in Odoo 22.
- Standard `create` is not idempotent. Because each JSON-2 call is its own transaction, "check for an existing operation, then create" done as two calls is racy and can leave partial state.
- Odoo 19 declares SQL constraints with `models.Constraint(...)`; `_sql_constraints` is no longer supported.

## Decision

1. The adapter uses **JSON-2 only**. No XML-RPC/JSON-RPC code paths.
2. Writes go through an `e_agent_bridge` addon. Each business command (`create_draft_purchase_order`, `amend_draft_rfq`, `create_draft_quotation`, `create_lead`) is **one** public model method. In a single call, and so in a single transaction, it:
   - inserts or looks up `e_agent.operation` keyed by `(namespace, company_id, operation_key)`, protected by `models.Constraint('UNIQUE(namespace, company_id, operation_key)', …)`;
   - if a row exists with the same `payload_digest`, returns the stored result; with a different digest, raises a conflict error;
   - otherwise validates draft-only preconditions, performs the create or write, and stores the result reference on the ledger row.
   Concurrent duplicates resolve by catching the unique violation, rolling back to a savepoint, and re-reading the row.
3. A reconciliation read method returns the ledger row for an operation key. It never returns fuzzy matches.
4. Reads use either narrowly named bridge read methods or allowlisted `search_read` on specific models and fields. There is no generic `execute(model, method, args)` exposed to the driver.
5. A dedicated Odoo user with an API key, minimal groups and company rules. The key lives in an operator-supplied secret, never in profiles or evidence.
6. At startup the adapter checks the Odoo server version, bridge module version and sandbox marker. It refuses to run against an unmarked or benchmark database.

## Alternatives considered

- **Standard `create` + correlation field + search.** Not atomic; research and design already reject it as a uniqueness guarantee.
- **XML-RPC for maturity.** Deprecated, with removal scheduled.
- **Direct PostgreSQL writes to Odoo's DB.** This bypasses ORM rules, access rights and computed fields. Rejected.

## Consequences

- Addon packaging and versioning become a release artifact separate from the Python wheels (`addons/e_agent_bridge`).
- Lost responses still produce `UNKNOWN` locally. Reconciliation by operation key normally resolves them to `COMMITTED` or "no row", where no row means no effect because the ledger row and the business record commit together.

## Verification

- Concurrency test: N parallel identical commands produce one business record. A different payload with the same key produces a conflict.
- Lost-response test: the proxy drops the response after commit; reconciliation finds the row and no duplicate is created on retry.
- Transaction test: a business validation failure leaves no ledger row.
- Revisit on an Odoo major upgrade, or if Odoo adds native idempotency keys to JSON-2.
