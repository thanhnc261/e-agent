---
name: eng-implement
description: Implement one task contract test-first inside its allowed paths, then gate and report.
---

# Engineering implement

Turn one task contract into a tested change. The contract, not the conversation, says what is in scope.

## Hard limits

- Read [eng-foundations](../eng-foundations/SKILL.md) first; cite rules by ID.
- Work only inside the contract's allowed paths (ENG-WORK-1); `uv run e-agent-harness check-scope` before every commit.
- No production code without a failing test watched first (ENG-WORK-2). A test that passes before the change exists tests the wrong thing.
- Refactors move code verbatim: `git mv`, contents changed only where a path is embedded, shown as renames in git.
- The trust anchor is not touched from outside the kernel (ENG-TRUST-1 to ENG-TRUST-5). A runtime feature ships behind `off | shadow | on` with its fallback boundary (ENG-TOGGLE-1, ENG-TOGGLE-2) and reports in readiness and evidence (ENG-TOGGLE-3).
- Code that touches the run store is written against the store conformance suite, for both stores (ENG-STORE-1).
- Never flip the feature's `passes` yourself; that is the close ritual in [eng-session](../eng-session/SKILL.md) with gate evidence (ENG-EVID-1).

## Workflow

1. **Read the contract** at `harness/state/<phase>/tasks/<id>.json`: feature ids, allowed paths, acceptance steps, gate set, base commit. Read the plan task it comes from.
2. **Pick the first acceptance step** and write the failing test for it. Run only that test; read the failure; it must fail for the missing behaviour, not for a typo.
3. **Implement the minimum** that makes it pass. Run the test, then the package's suite (`uv run e-agent-harness gate quick --package <pkg>`).
4. **Repeat** per acceptance step. Keep each commit to one step where the tests allow it.
5. **Architecture while you go:** layer direction (ENG-ARCH-1), portable contracts (ENG-ARCH-2), composition at bootstrap (ENG-ARCH-3), no speculative structure (ENG-ARCH-4), namespace layout (ENG-ARCH-5).
6. **When the plan is wrong:** decide the smallest change that satisfies the spec, record the ruling (what, why, cost if wrong) for the handoff, and update the plan in the same commit (ENG-PLAN-3). A contract or boundary change stops for an ADR (ENG-PLAN-2).
7. **Checkpoint** with `uv run e-agent-harness checkpoint --session <id> --next "<step>"` at natural breaks.
8. **Report** at the end: each test by name with its red-then-green run, the commands run with their output, the evidence path from the gate, and every deviation as a ruling. "Should pass" is not a report (ENG-EVID-2).

## Before handing off

- [ ] Every acceptance step has a named test that was watched failing and then passing.
- [ ] `check-scope` passes; the diff touches only allowed paths.
- [ ] The gate set of the contract passed on the clean commit (evidence path noted).
- [ ] Rulings and plan updates are in the same commits as the deviations.

## Stop gate

Hand to the close ritual in [eng-session](../eng-session/SKILL.md). Verification beyond the gate set is [eng-verify](../eng-verify/SKILL.md); the independent review is [eng-review](../eng-review/SKILL.md).
