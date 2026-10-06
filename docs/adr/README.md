# Architecture decision records

One decision per ADR. Statuses: **Proposed** (recommended, not yet accepted by the project owner), **Accepted**, **Superseded by NNNN**, **Rejected**. A proposed ADR does not change the baseline until accepted. When one is accepted, update the affected design sections in the same change.

| ADR | Title | Status | Gates |
|---|---|---|---|
| [0001](0001-local-mvp-scope.md) | Local-first MVP with streaming UI and broader ERP tasks | Accepted (user-selected scope) | Plan scope |
| [0002](0002-capability-naming-and-domain-packs.md) | Capability naming by business context; domain pack structure | Proposed | I02 |
| [0003](0003-durability-ownership.md) | Kernel ledger owns side-effect durability; no framework durability in MVP | Proposed | I05 |
| [0004](0004-agent-driver-integration.md) | Pydantic AI 2.x driver: deferred-only writes, continuation hygiene | Proposed | I04 |
| [0005](0005-odoo-integration-transport.md) | Odoo 19 JSON-2 transport and transactional bridge commands | Proposed | I06 |
| [0006](0006-approval-digest-canonicalization.md) | Approval digest uses an RFC 8785 (JCS) profile | Proposed | I02 |
| [0007](0007-run-event-stream-contract.md) | Durable run events over SSE; framework UI protocols are adapters | Proposed | I08 |
| [0008](0008-observability.md) | OpenTelemetry with GenAI conventions, separate from evidence | Proposed | I01 |
| [0009](0009-rule-inventory-and-enforcement-engines.md) | Rule inventory declares an enforcement engine per rule | Proposed | I03 |
| [0010](0010-evaluation-protocol.md) | Evaluation protocol: pass@1 in development, pass^k at release | Proposed | I04 |
| [0011](0011-layered-replaceable-ui.md) | Layered, themeable and replaceable UI over a shared headless core | Proposed | I08 |
| [0012](0012-schema-driven-integration-management.md) | Schema-driven integration, connection and credential management | Proposed | I06 (seams); admin UI Phase 2 |

The [2026-10-06 architecture review](../reviews/2026-10-06-architecture-review.md) explains the findings behind 0002–0010. ADR 0012 comes from [integration management](../integration-management.md). ADR 0011 comes from the follow-up UI research in [UI architecture](../ui-architecture.md).

## Mapping from research 08 proposals

Research 08 listed ten candidate ADRs with a different numbering. Their content is already the HLD/MVP baseline. Do not reuse their numbers.

| Research 08 proposal | Where it is decided now |
|---|---|
| 001 Deployment, 002 Dependency direction, 003 Public surface | HLD §4 |
| 004 Agent execution | HLD §6, ADR 0001, ADR 0004 |
| 005 Plugin activation | MVP design §6 |
| 006 Side effects | MVP design §7–9, ADR 0003, ADR 0005 |
| 007 Semantic ownership | HLD §7, ADR 0009 |
| 008 Persistence | HLD §8, MVP design §9, ADR 0003 |
| 009 Compatibility | HLD §8 |
| 010 Product evidence | MVP design §11, ADR 0007 |

## Template

```markdown
# ADR NNNN: <decision in a few words>

Date: YYYY-MM-DD. Status: Proposed | Accepted | Superseded by NNNN | Rejected.

## Context
Forces, constraints, evidence (with sources).

## Decision
What is decided, stated so it can be checked.

## Alternatives considered
Each with why it was not chosen.

## Consequences
Positive, negative, follow-up work; compatibility/migration impact.

## Verification
Tests or gates that show the decision holds; revisit triggers.
```
