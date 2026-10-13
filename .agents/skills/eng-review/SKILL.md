---
name: eng-review
description: Review a task or phase against its contract and the ENG rules; writes review JSON.
---

# Engineering review

An independent judgement of one task or phase. The reviewer sees the contract, the diff and the evidence, never the implementer's reasoning, and runs in a fresh context.

## Hard limits

- Read [eng-foundations](../eng-foundations/SKILL.md) first; cite rules by ID. Never restate a rule.
- Read-only: never edit the code, tests, evidence or contract under review. Write only the review JSON.
- Report findings that affect correctness or the contract; everything else is optional and marked `style`. A reviewer asked to find gaps will find some; chasing them all leads to over-engineering.
- One severity per finding, with file and line (or evidence path) and the rule or acceptance step it violates. A Blocker rests on a rule enforced by `gate`, `test`, `hook` or `permission`, or on an accepted ADR.
- Trust-anchor and kernel tasks are reviewed by the other provider (H0 decision); the review says which provider ran it.

## Inputs

- The contract `harness/state/<phase>/tasks/<id>.json` and the plan task it names.
- The diff: `git diff <base_commit>...HEAD --stat` then the files.
- The gate evidence the feature cites, and `uv run e-agent-harness close-check` output.
- The feature entry in `harness/state/<phase>/features.json`.

## Workflow

Apply [rubric.md](references/rubric.md) in order. For each area record findings; stop at the first Blocker only if it makes the rest meaningless.

1. Scope and contract: allowed paths respected, every acceptance step demonstrated, `passes` evidence ties to a clean commit (ENG-WORK-1, ENG-EVID-1).
2. Trust anchor (ENG-TRUST-1 to ENG-TRUST-5).
3. Toggles and fallback (ENG-TOGGLE-1 to ENG-TOGGLE-3).
4. Both stores (ENG-STORE-1).
5. Architecture and import contracts (ENG-ARCH-1 to ENG-ARCH-5).
6. Tests are honest: watched red, assert real behaviour, no mock of the thing under test (ENG-WORK-2).
7. Link and path hygiene: no broken relative links, no stale paths after a move (ENG-DOC-1).
8. Evidence and secrets: separate fixture and live results, nothing redacted by hand, no key material (ENG-EVID-2, ENG-EVID-3, ENG-BOUND-3).

Write `harness/state/<phase>/reviews/<task>.json` from [review.json](templates/review.json) and validate it:

`uv run e-agent-harness validate review harness/state/<phase>/reviews/<task>.json` must print ok.

Verdict `rework` when any finding affects `correctness` or `contract`; otherwise `accept`.

## Before handing off

- [ ] Every finding has an id, one severity, `affects`, a summary and evidence.
- [ ] The verdict follows from the findings.
- [ ] The JSON validates and names the provider and `fresh_context: true`.

## Stop gate

The implementer answers each `correctness` or `contract` finding with a fix or a ruling, then the task re-enters the close ritual. A review never flips `passes`.
