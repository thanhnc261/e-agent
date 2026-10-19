# ADR 0024: Approval model for multi-step plans

Date: 2026-10-14. Status: Accepted (owner, 2026-10-18, gate G1 of the Phase 2 plan). Refines ADRs 0006, 0014, 0019; MVP design §7, §10; [target architecture](../design/target-architecture.md) §6.4.4, §6.4.9.

## Context

ERP-Bench-style tasks need several dependent writes in one run (Odoo plan Phase 0.1), and some benchmark instructions say "do not ask for confirmation". e-agent's trust anchor requires approval of the exact normalized action (ENG-TRUST-3). The roadmap default is "approve the plan once".

The owner decided on 2026-10-14 ([adoption review](../reviews/2026-10-14-x-agent-adoption-review.md) D-3 and D-4):
- D-3: a benchmark-only auto-approve profile is allowed, but only for low-risk effects.
- D-4: nothing is modified after approval.

## Decision

- **Approve the plan once.** The approver approves the plan digest (ADR 0025): every step's normalized action, lineage placeholders and dependencies. One approval authorizes the steps in order, and each step is still revalidated before it reserves. Any deviation stops the plan and returns findings: stale facts, a changed policy or credential, a lineage value outside its rule, or a failed step. A changed plan is a new proposal that needs a new approval.
- **Presentation.** The approval shows every step with its arguments, placeholders shown as "from step N: <path>", the highest declared `risk` and every irreversible step (ADR 0029). A 1-step plan is presented exactly as today's action.
- **Benchmark auto-approve (D-3).**
  - It exists only in a profile marked benchmark-only (`operator.benchmark_auto_approve: true`) and never with `environment: live`; startup refuses that combination.
  - It covers only steps with `risk` `read` or `write_low` and no defaulted declaration. A plan containing any `write_high` or `destructive` step needs a human approval for the whole plan.
  - `/health/ready` reports the flag the way it reports `self_approval_allowed` (ADR 0019).
  - The evidence bundle records every auto-approval as such, with the system actor.
- **Nothing modifies an action after its approval digest (D-4).**
  - A guardrail, rule or kernel step may change an argument only before the digest is computed, and the approver sees the original and adjusted values.
  - A model's text reply may be redacted at any time, because it changes no external data.
  - The presentation field for adjustments arrives with the first guardrail ADR that needs it; Phase 2 adds no field.
- **Self-approval** rules (ADR 0019) apply to plan approval unchanged.

## Alternatives considered

- Approve each step: rejected as the default. It multiplies prompts for one intent, invites fatigue (threat T20), and later steps cannot be approved with values that only exist at run time. Plan approval binds the placeholders and their rule instead.
- No auto-approve at all: rejected by the owner (D-3). Benchmark evaluation needs unattended runs. The risk limits and the live refusal keep it out of production.
- Auto-approve for every risk in benchmark profiles: rejected. A benchmark profile can still reach a real ERP; `write_high` and `destructive` effects always need a human.
- Guardrails that modify actions after approval: rejected (D-4). The executed action would differ from the approved digest.

## Consequences

- Code: approval flow approves a plan digest; presentation gains plan steps; profile flag, startup refusal and readiness field; an auto-approval path in the kernel that records the system actor; the live guard from ADR 0025.
- Tests and evidence: plan approved once and dispatched in order; approval for another digest rejected; stale before step 2 stops the plan; auto-approve refused with `environment: live`; auto-approve refused for a `write_high` step; readiness reports the flag; evidence marks auto-approvals.
- Operations: release qualification (ADR 0010) runs with auto-approve off unless the report states otherwise. Threat model T20, T21 and T22.

## Gates

Phase 2 Task 2c.7 for plan approval and presentation (`full`, `pg`). Benchmark auto-approve is implemented with Phase 5 evaluation, after ADR 0029's declarations exist.
