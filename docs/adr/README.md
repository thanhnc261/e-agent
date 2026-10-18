# Architecture decision records

One decision per ADR. Statuses: **Proposed** (recommended, not yet accepted by the project owner), **Accepted**, **Superseded by NNNN**, **Rejected**. A proposed ADR does not change the baseline until accepted. When one is accepted, update the affected design sections in the same change.

| ADR | Title | Status | Gates |
|---|---|---|---|
| [0001](0001-local-mvp-scope.md) | Local-first MVP with streaming UI and broader ERP tasks | Accepted (user-selected scope) | Plan scope |
| [0002](0002-capability-naming-and-domain-packs.md) | Capability naming by business context; domain pack structure | Accepted | I02 |
| [0003](0003-durability-ownership.md) | Kernel ledger owns side-effect durability; no framework durability in MVP | Accepted | I05 |
| [0004](0004-agent-driver-integration.md) | Pydantic AI 2.x driver: deferred-only writes, continuation hygiene | Accepted | I04 |
| [0005](0005-odoo-integration-transport.md) | Odoo 19 JSON-2 transport and transactional bridge commands | Accepted | I06 |
| [0006](0006-approval-digest-canonicalization.md) | Approval digest uses an RFC 8785 (JCS) profile | Accepted | I02 |
| [0007](0007-run-event-stream-contract.md) | Durable run events over SSE; framework UI protocols are adapters | Accepted | I08 |
| [0008](0008-observability.md) | OpenTelemetry with GenAI conventions, separate from evidence | Accepted | I01 |
| [0009](0009-rule-inventory-and-enforcement-engines.md) | Rule inventory declares an enforcement engine per rule | Accepted | I03 |
| [0010](0010-evaluation-protocol.md) | Evaluation protocol: pass@1 in development, pass^k at release | Accepted | I04 |
| [0011](0011-layered-replaceable-ui.md) | Layered, themeable and replaceable UI over a shared headless core | Accepted | I08 |
| [0012](0012-schema-driven-integration-management.md) | Schema-driven integration, connection and credential management | Accepted | I06 (seams); admin UI Phase 2 |
| [0013](0013-integration-auth-sdk-and-delegated-connections.md) | Integration auth SDK, tenant app registrations and user-delegated connections | Accepted | I02/I06 (contracts, MVP subset); Phase 2 |
| [0014](0014-mvp-remediation-boundaries.md) | MVP remediation boundaries, approval freshness and external uncertainty | Accepted (approved remediation plan) | FIX-02..06 |
| [0015](0015-task-workspace-presentation.md) | Task workspace and host-owned presentation metadata | Accepted (requested UI implementation) | UI redesign / I08–I09 |
| [0016](0016-selectable-agent-surfaces.md) | Selectable enterprise agent surfaces | Accepted (requested overlay design) | UI surfaces / I08–I09 |
| [0017](0017-member-discovery-read-models.md) | Member-readable task catalog and connection projections | Accepted (requested overlay adoption, API-01) | Enterprise overlay / API-01, FE-06 |
| [0018](0018-run-transitions-reason-codes-event-attribution.md) | Run transition table, reason codes, event actor, paged events | Accepted (2026-10-14) | WP1 Tasks 2, 4, 5, 7 |
| [0019](0019-approval-reachability-and-self-approval.md) | Approval expiry sweeper; self-approval forbidden unless profile allows | Accepted (2026-10-14) | WP1 Tasks 3, 6 |
| [0020](0020-connection-level-write-admission.md) | Reservation refused while the connection has an unresolved write | Accepted (2026-10-14) | WP1 Task 8 |
| [0021](0021-litellm-model-provider.md) | LiteLLM as an explicit, opt-in second model provider; Ollama stays default | Accepted (2026-10-14) | WP1 Task 10 |
| [0022](0022-conversational-turns-read-feedback-discovery.md) | Rejected reads as feedback, conversational replies, open-demand discovery | Accepted (2026-10-14) | Real-agent plan Tasks 2–4 |
| [0024](0024-plan-approval-model.md) | Approval model for multi-step plans: approve the plan once; benchmark-only auto-approve for low risk; no modification after approval | Accepted (2026-10-18) | Phase 2 Task 2c.7; auto-approve with Phase 5 |
| [0025](0025-execution-ir.md) | Execution IR: action plans, lineage, plan digest, step dispatch, partial failure; widens the ADR 0018 table | Accepted (2026-10-18) | Phase 2 Tasks 2c.1, 2c.3–2c.9 |
| [0026](0026-plugin-layout-and-reusable-core.md) | Plugin layout and a reusable core: `plugins/<area>/<package>`, core never imports plugins, plugins are guests on a common SDK, required features enforced, no ERP in the server | Accepted (2026-10-15, amended: common plugin SDK) | Phase 1d (owner gate G1) |
| [0027](0027-feature-toggles.md) | Feature toggles `off/shadow/on` with shadow comparison and pre-reservation fallback | Accepted (2026-10-18) | Phase 2 Part 2b |
| [0028](0028-task-definitions.md) | Task definitions with acceptance specs as domain-pack resources | Accepted (2026-10-18), with the answer-condition amendment (accepted 2026-10-18) | Phase 2 Tasks 2c.1, 2c.2, 2c.6 |
| [0029](0029-capability-effect-declarations.md) | Capability effect declarations: risk, reversibility, idempotency | Accepted (2026-10-18) | Phase 2 Tasks 2c.1, 2c.2, 2c.7, 2c.8 |
| [0030](0030-data-governance.md) | Data classification, minimization, retention and deletion for run data | Proposed | Startup rule Phase 2/3; minimization Phase 3; markers and export authorization Phase 5; retention and deletion Phase 7 |

The [2026-10-06 architecture review](../reviews/2026-10-06-architecture-review.md) explains the findings behind 0002–0010. ADR 0012 comes from [integration management](../design/integration-management.md), ADR 0013 from [integration auth SDK](../design/integration-auth-sdk.md). ADR 0011 comes from the follow-up UI research in [UI architecture](../design/ui-architecture.md). ADR 0030 decides [data governance](../design/target-architecture.md#133-data-governance-p) (target §13.3). ADRs 0024, 0025, 0027–0029 decide the [execution IR section](../design/target-architecture.md#64-execution-ir-p) (target §6.4). Number 0023 (conversations, Phase 4) is reserved.

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
