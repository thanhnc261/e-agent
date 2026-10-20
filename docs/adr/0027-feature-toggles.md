# ADR 0027: Feature toggles with shadow comparison and pre-reservation fallback

Date: 2026-10-14. Status: Accepted (owner, 2026-10-18, gate G1 of the Phase 2 plan). Refines roadmap rule 3 and ENG-TOGGLE-1..3; [target architecture](../design/target-architecture.md) §6.4.8.

Refined by [ADR 0023](0023-conversation-model.md) (accepted at gate G-A, 2026-10-20) for `features.conversations` only: its `shadow` links runs to conversations and writes conversation rows, and adds no driver call, provider read, budget use, refusal or carried context (ADR 0023 §9).

## Context

Roadmap rule 3 requires every new runtime feature (execution IR, ContextAssembler, conversations, grounded answers, action plans) to ship behind a profile toggle `off | shadow | on`, with fallback only before a write is reserved. Nothing in the code implements it: the `Profile` record in `server/profile.py` has no `features` field, and no `feature.fallback` event exists. Phase 2's first runtime task (2b.1) builds it, and every later phase uses it. The [adoption review](../reviews/2026-10-14-x-agent-adoption-review.md) (XA-24) adds that a shadow path must have a real comparison consumer, and that a toggle is not cover for a stub.

## Decision

- `Profile.features` is a record `Features` with one field per feature, each a `FeatureMode` (`off`, `shadow`, `on`). It defaults to all `off`. An unknown feature name is a validation error (`extra="forbid"`). A profile without `features` loads as all `off`.
- `off` is exactly today's behaviour: no new event, record or code path is reached. A golden event stream recorded before the feature lands proves it.
- `shadow` computes the new path and records a **comparison with the live path** (for example "compiled step digest equals action digest"). It acts on nothing and adds no driver call, provider read or budget use. A shadow failure records the feature's own shadow-failure event (`ir.shadow_failed` for `execution_ir`, ADR 0025) and changes nothing else; for `execution_ir`, a run that resolves no task definition is such a failure, with `IR_TASK_UNRESOLVED` (ADR 0028).
- `on` uses the new path. It falls back to the existing path only **before the first write reservation**, recording `feature.fallback` with `feature`, a typed `reason_code` (a `ReasonCode` member the feature's ADR names) and the fixed, safe message the kernel keeps for that code; callers pass no text (amended 2026-10-18 by review finding 2b.2 R-1, PR-25, PR-28). A fallback code is carried only by that event (and, for an unresolved task, by `ir.shadow_failed`) and never ends a run. After a reservation there is no fallback: the run fails closed or goes to reconciliation. Fallback never bypasses approval, admission, verification or the transition table.
- `/health/ready` returns `features` with each mode, and the evidence bundle records the same object as an additive key under `e-agent-evidence-v1`.
- A mode a profile can select is complete and tested. A toggle never hides a stub.
- Committed profiles keep every new feature `off` until the owner turns it on.

## Alternatives considered

- Boolean flags (`*_ENABLED`): rejected because they have no shadow mode, so a new path cannot be compared with the old one before it acts.
- Per-tenant or runtime-switchable flags in the database: deferred until there are several tenants. Profiles are per deployment today.
- Environment-variable flags: rejected because typed profile settings are validated at startup and reported, while environment flags are neither (XA-14).

## Consequences

- Code: new `contracts/features.py`; `Profile.features`; the coordinator receives the features; a `feature.fallback` event type and reason codes; a kernel helper that records a fallback; readiness and evidence fields.
- Tests and evidence: profile default and unknown-name tests; an `off`-mode golden event stream; a shadow-cost test (no extra calls, reads or budget); readiness and evidence tests. `/health/ready` and the evidence route return untyped mappings, so the OpenAPI document and the UI client change only if a typed response model does.
- Operations: operators see the modes in `/health/ready`, and release reports record them.

## Gates

Phase 2 Tasks 2b.1–2b.3 ([plan](../plans/2026-10-14-phase2-execution-ir.md)): gate `full` for all three, plus `pg` for 2b.1 and 2b.2 and `e2e` (`make e2e`) for 2b.3.
