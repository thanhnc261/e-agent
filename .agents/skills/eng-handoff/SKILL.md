---
name: eng-handoff
description: Write the task handoff JSON and the phase handoff document the owner reads.
---

# Engineering handoff

A handoff says what changed, what was verified with its output, what was decided and what remains. It reports failures and skipped checks by name (ENG-DOC-2, ENG-EVID-2).

## Hard limits

- Read [eng-foundations](../eng-foundations/SKILL.md) first; cite rules by ID.
- No claim without an evidence reference: a gate evidence path, a test name with its run, a commit.
- Every deviation from the plan is a ruling with its cost if wrong. Every change outside the repository has its undo.
- No key material, ever (ENG-BOUND-3, ENG-EVID-3).

## Two artifacts

**1. The task handoff JSON** at `harness/state/<phase>/handoffs/<task>.json`, required by `close-check`:

| Field | Content |
|---|---|
| `task` | the contract id |
| `changed` | one paragraph: what the task did, in product terms |
| `evidence_refs` | the `harness/state/evidence/…` paths the task relies on (gate evidence first) |
| `open_items` | what remains, each one sentence |
| `rulings` | `{ "ruling": "...", "cost_if_wrong": "..." }` per deviation |
| `outside_repo` | `{ "change": "...", "undo": "..." }` per change outside the repository (empty list when none) |

Validate with `uv run e-agent-harness handoff <task>`; it checks the schema and that every evidence reference exists.

**2. The phase handoff document** at `docs/handoffs/<YYYY-MM-DD>-<topic>.md` from [handoff.md](templates/handoff.md), written at the end of a phase and for any task the owner must read. The document carries the key numbers and the gate output verbatim so the owner does not have to open evidence files.

## Workflow

1. Collect: the contract, the commits since its base (`git log --oneline <base>..HEAD`), the gate evidence files, the review JSON, the progress log entries for the task.
2. Write the JSON; run `uv run e-agent-harness handoff <task>` until it prints ok.
3. For a phase: write the document with every section of the template; paste the verification output rather than summarising it.
4. Commit the handoff with the other bookkeeping (`harness/state/**`, `docs/handoffs/**`), then run `close-check`.

## Before handing off

- [ ] The JSON validates; every evidence reference exists.
- [ ] Each ruling has its cost if wrong; each outside-repository change has its undo.
- [ ] Skipped verification levels are named with their blocker.
- [ ] The document (for a phase) has every template section and the gate output verbatim.

## Stop gate

`close-check` passes with the handoff in place. A handoff that hides a failure is worse than no handoff.
