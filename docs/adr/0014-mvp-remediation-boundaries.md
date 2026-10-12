# ADR 0014: MVP remediation boundaries and uncertainty

Date: 2026-10-07. Status: Accepted (user approval of the [remediation plan](../reviews/2026-10-07-mvp-fix-plan.md), 2026-10-07). Refines ADRs 0003, 0005, 0006 and 0007.

## Context

The independent MVP review found stale authority, incomplete recovery and read-back, and gaps between the selected design and implementation. The approved plan retains the modular monolith, provider-neutral contracts, host-owned authorization and durability, local inference, and eight ERP tasks.

## Decision

- Database work claims, lease renewal, fencing and local state changes use short transactions. No database transaction spans inference or ERP transport. An optional session advisory lock may serialize a connection across transport; it does not prove that an expired worker's external call stopped. ERP operation uniqueness and reconciliation remain necessary. This clarifies ADR 0003's transaction-scoped lock wording.
- A negative operation lookup during an uncertain or in-flight call does not prove no effect. Reconciliation remains unresolved until authoritative evidence is available. A duplicate-in-flight or operation-identity conflict cannot establish that the logical operation did not commit. This qualifies ADR 0005's consequence about absent operation rows.
- Approval binds current policy, semantic rule bundle, admitted surface, connection and non-secret credential revisions, plus source revisions or material-fact digests. The gateway refreshes facts and validators before dispatch. The host retains authorized approved facts for domain verifiers to compare unchanged material fields; model output cannot supply these snapshots.
- Approval evidence and its action transition commit atomically. A queued approval slot is keyed by exact action, digest and run revision; an identical payload is idempotent and conflicting decisions/actors are rejected before dispatch.
- API work admission is persisted atomically before acceptance. A replacement worker recovers from the effect ledger; it does not replay an interrupted business command. Fencing prevents stale local commits but is not external exactly-once execution.
- Public model text uses a narrow SDK sink and transient stream/message offsets separate from durable SSE sequence IDs. Only public text parts are emitted; reasoning and tool arguments are excluded. Bounded prefixes support reconnect snapshots. Final public text and business events remain durable.
- An identical repeated independently verified structured answer finishes without repeating verification or another inference call. Intermediate verified answers may still precede a different approved action; they must not prematurely terminate that workflow.
- Plain model text cannot finish a business task without an independently verified outcome. The driver receives bounded host feedback to propose a structured answer or the requested action. The task-specific qualification oracle must still reject unrelated verified answers.
- Clarification input resumes the same persisted run with requester authorization and revision checks. Active-time, token and provider/model deadline budgets exclude human waiting and survive continuation checkpoints. The measured local candidate uses a 32,000 cumulative input/output-token cap, 120 active seconds, 60 seconds per model call and 20 seconds per provider call. The earlier 16,000-token candidate exhausted its cap during verified-answer acknowledgement; its failed trials are retained. These host defaults are configuration, not model-granted authority.
- Live plugin admission requires an externally trusted artifact inventory covering code, parents, manifest and resources before import. Editable fixture admission is explicit and does not qualify live integrity.

## Consequences

Migration 0003 adds durable work scheduling. Portable action records gain optional non-secret credential revision and host-retained approved facts; older amendments without a baseline fail verification safely. OpenAPI and generated client types must change together. Secrets stay outside these records. Odoo bridge source version 19.0.0.3.0 requires separately verified sandbox installation.

The source changes alone do not establish local MVP readiness. Owner Odoo identity, bridge installation, live races, integrated persistent model/UI trials and human approval evidence remain release gates. Desktop, live BigQuery and full knowledge governance remain deferred.

## Verification

Run memory/PostgreSQL store conformance, stale approval and credential rotation tests, artifact tampering before import, independent field corruption, clarification and transient streaming tests, actual process-death recovery, UI host conformance, and clean installed-wheel closure. Live provider tests and qualification must report blocked prerequisites honestly.
