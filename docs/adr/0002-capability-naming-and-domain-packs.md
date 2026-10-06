# ADR 0002: capability naming by business context; domain pack structure

Date: 2026-10-06. Status: Accepted (project owner, decisions D1–D5, 2026-10-06).

## Context

The HLD separates domain, capability contract, implementation binding and connection. Yet its example capability ID is `erp.purchase-order.create-draft.v1`, and "ERP" is a provider category, not a business domain. ADR 0001 adds tasks across procurement, inventory, sales, CRM and receivables, all implemented by Odoo, plus BigQuery analytics. ERP-07 creates a CRM lead in Odoo, while the HLD lists live CRM as out of scope and research 10 proposes a future `domain-crm` that a non-Odoo CRM could implement. If contract IDs carry the provider category, a second CRM provider would need a different contract for the same business operation.

## Decision

1. Capability contract IDs are `<bounded-context>.<entity>.<operation>.v<major>`. Initial contexts are `procurement`, `inventory`, `sales`, `crm`, `receivables` and `analytics`. Examples: `procurement.purchase-order.create-draft.v1`, `inventory.availability.read.v1`, `crm.lead.create.v1`, `receivables.overdue-invoices.summarize.v1`.
2. Binding IDs carry the provider, for example `odoo19.procurement.purchase-order.create-draft`. Connection IDs carry the tenant/account.
3. Keep **one** `e-agent-domain-erp` distribution for the MVP. Inside it, each bounded context gets its own module (`domain_erp.procurement`, `.inventory`, `.sales`, `.crm`, `.receivables`) with its own DTOs, shapes, rules and verifiers. Modules do not import each other's internals. Workflows that span contexts live in application modules.
4. `e-agent-domain-analytics` is a separate distribution (ADR 0001/I12) because it has a different owner, data and risk profile.
5. "Live CRM out of scope" in the HLD means **external CRM providers** (Salesforce, HubSpot and similar). Odoo CRM records used by ERP-07 are in scope as an Odoo binding of `crm.lead.create.v1`.

## Alternatives considered

- **Keep `erp.` prefixes.** Simple, but it bakes the provider category into contracts and contradicts HLD §5.
- **One distribution per bounded context now.** This gives clean ownership, but adds five packages with one owner and no independent release need. Research 10 advises against empty or speculative packages.
- **Provider-agnostic "universal business object" contracts.** Rejected by HLD §5.

## Consequences

- MVP design examples and the rule inventory use the new IDs.
- A bounded-context module can be split into its own distribution later without changing contract IDs.
- Import-linter gets "independence" contracts between the `domain_erp.*` context modules.

## Verification

- Architecture gate: `domain_erp` context modules are mutually independent (import-linter `independence` contract).
- Registry test: two bindings (Odoo and a fixture CRM) of `crm.lead.create.v1` on two connections resolve correctly.
- Revisit when a second team owns a context or a context needs an independent release cadence.
