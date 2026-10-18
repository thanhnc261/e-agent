# ADR 0025: Execution IR: action plans, lineage, plan digest, step dispatch and partial failure

Date: 2026-10-14. Status: Accepted (owner, 2026-10-18, gate G1 of the Phase 2 plan). Refines ADRs 0003, 0004, 0006, 0014, 0018, 0020; MVP design §7, §9; [target architecture](../design/target-architecture.md) §5.4, §6.4.3–§6.4.7, §17 C8.

## Context

A run admits one write today (`Budgets.max_admitted_writes = 1`). Phase 5 needs runs with several dependent writes, such as a sales order and then a purchase order whose origin is that order's name. That changes trust-anchor invariants: what one approval covers, per-step reservation under the connection rule (ADR 0020), partial failure, and argument values that are only known at run time. The [design principles review](../reviews/2026-10-14-design-principles-review.md) DR-01 made the design section and this ADR the Phase 2 entry gate. ADR 0018 locks the run transition table and says that widening it needs a new ADR; this is that ADR.

## Decision

- **Records** are as in target §6.4.3: `ActionPlan`, `PlannedStep`, `LineageRef(step_id, path)`. A placeholder is a `LineageRef` inside a step's proposal arguments; `PlannedStep` has no separate lineage field.
  - Each plan step yields exactly one `ActionRecord`, which gains nullable `plan_id` and `step_index`.
  - `StepRecord` (target §5.4) records kernel stages and driver turns, links to actions through `action_id`, and is written in the same transaction as its run events.
- **The driver port** gains `ProposePlan(plan)` in `DriverStep`. A single `ProposeAction` compiles to a 1-step plan. A model-chosen connection is refused, as today.
  - `ProposePlan` and `DriverInput.allowed_capabilities` (the run's tool set, ADR 0028) are both additive and share one `sdk_api` minor bump (`SDK_API_VERSION` `1.0` to `1.1`; the existing `>=1.0,<2.0` manifest ranges still admit). Task 2c.6 adds the field with a `None` default and Task 2c.9 adds `ProposePlan` and makes the bump; nothing is released in between.
- **Validation:**
  - structure is checked by the records (unique ids; acyclic, known dependencies; lineage names a dependency);
  - policy is checked by a pure kernel function (capabilities inside the task definition; write count at most `max_admitted_writes`; every step a write or an answer, never a read (amended 2026-10-18 by review finding 2c.4 R-3); arguments inside the digest profile; per-step domain validation and policy, with placeholders typed by their input schemas).
- **Lineage** has one rule: copy the value at a JSON pointer from the earlier step's **verified outcome**, never from a receipt or from model output, and check its type. A new rule kind needs a new ADR.
- **Digest** (refines ADR 0006):
  - a placeholder is encoded as `{"$lineage": {"step", "path"}}`, and a literal `$lineage` key is refused;
  - the plan digest is `jcs-sha256-v1` over the ordered steps' ids, sorted dependencies and step digest inputs (target §6.4.4);
  - a 1-step plan's approval digest equals today's action digest byte for byte.
- **Dispatch:**
  - serial in step-index order; step N + 1 starts only after step N is `VERIFIED`;
  - before each reservation the kernel revalidates facts, policy, connection and credential versions, approval TTL and lineage, and records the resolved values;
  - each step reserves under its own logical operation id;
  - ADR 0020 applies unchanged.
- **Transition table** (widens ADR 0018):
  - new pairs `VERIFYING → RUNNING` (step verified, steps remain) and `RUNNING → VERIFYING` (a later step committed);
  - the existing defensive pair `RUNNING → NEEDS_RECONCILIATION` gains a call site (a later step `UNKNOWN`);
  - no other pair changes.
- **Reason codes:**
  - codes do not depend on plan length: a step's outcome uses today's codes (`EFFECT_UNKNOWN`, `PROVIDER_ERROR`, `VERIFICATION_FAILED`, `STALE`, `CONNECTION_BUSY`, …) and today's `classify` groups, and the step is identified by `plan_id` and `step_index`;
  - one new run-outcome code, `PLAN_LINEAGE_REJECTED`, classified blocked-by-design (with `ACCEPTANCE_UNMET` from ADR 0028, classified failed);
  - the fallback codes `IR_TASK_UNRESOLVED`, `IR_COMPILE_FAILED` and `IR_VALIDATION_FAILED` (ADR 0027) are `ReasonCode` members carried only by `feature.fallback` events, and `IR_TASK_UNRESOLVED` also by `ir.shadow_failed` (ADR 0028); they never end a run.
- **Partial failure** follows target §6.4.6:
  - committed steps are never replayed (ENG-TRUST-5);
  - an `UNKNOWN` step stops the remainder and goes to reconciliation;
  - the outcome and evidence report each step as verified, committed, unknown, failed or unstarted.
- **Toggle** `features.execution_ir` (ADR 0027), with the fallback boundary at the first `reserve_operation`.
- **Live guard:** a profile with `environment: live` refuses `max_admitted_writes > 1` until a UI can present and recompute a multi-step plan (Phase 5).


### Amendment: plan resume after a crash (proposed 2026-10-18; the owner accepts before the phase merges)

A plan whose latest step is `VERIFIED` and whose next step is unstarted resumes after a crash, but never inside startup recovery or an operator call. Recovery never sends a write (ADR 0018, MVP §9). It enqueues one fenced `resume` work item, de-duplicated like `expire`, and returns. The worker claims the item under the fence. It re-checks under the claim that the run is `RUNNING` or `VERIFYING` with plan state; otherwise it drops the item. Then it continues the plan through the same path as a live finish, so every pre-reservation guard applies again (approval TTL, the approved step input, fact, rule and policy staleness, domain validation of resolved lineage values). A latest step in `UNKNOWN` never resumes; it goes to reconciliation. A resume is attempted at most once. A failed resume claim never enqueues another resume, and a claim taken over from a dead owner (fence above 1) counts as failed, even if the owner never started. The run then goes through the crash rules with resume disabled: `FAILED` `INTERRUPTED` if nothing was reserved for the next step, reconciliation if a reservation or dispatch exists. Nothing is re-sent. The work kinds gain `resume` (`contracts/work.py`, migration `0006`). The 2c.8 review R-1 found that a resume inside unfenced startup recovery could misreport a committed step when two processes start on one ledger.

## Alternatives considered

- One approval per step: rejected as the default because it multiplies approval prompts for one business intent, and later steps cannot be shown with their final values. See ADR 0024.
- A general rule language for lineage (patterns, ranges, lookups): deferred until a Phase 5 capability needs it. Copy-from-verified-outcome covers the known patterns and is checkable.
- Parallel dispatch of independent steps: deferred. Serial dispatch fits the connection-level admission rule, and parallelism needs the durable writer lease (Phase 6).
- A framework graph runtime (LangGraph and similar) for plans: rejected. The kernel owns the state machines (ENG-TRUST-2, C6).

## Consequences

- Code: `contracts/plan.py`, `contracts/step.py`, `contracts/action.py` (`plan_id`, `step_index`), `contracts/task.py` (ADR 0028), `contracts/run.py` (pairs, codes), `contracts/events.py` (`ir.plan_compiled`, `ir.shadow_failed`, `ir.lineage_resolved`, `ir.step_verified`); `kernel/ir.py`, `kernel/step.py`, approval, dispatch, transitions, recovery, evidence; `sdk/ports.py`; migration `0005_action_plans_and_steps.sql`; both stores; the driver.
- Tests and evidence: plan digest golden vectors (Python and TypeScript for the 1-step case); 1-step equivalence; lineage resolution and rejection; stale before step 2; `UNKNOWN` blocks the remainder; no fallback after the first reservation; recovery without replay; store conformance on both stores; notes-domain two-step plan.
- Operations: the evidence bundle gains additive `plan` and `steps` keys; multi-write plans run only in fixture profiles in Phase 2.

## Gates

Phase 2 Tasks 2c.1 and 2c.3–2c.9, gates `full` and `pg`; end-of-phase levels 1–4.
