---
name: eng-verify
description: Run the four verification levels in order and record evidence; refuses a dirty tree.
---

# Engineering verify

Verification is the highest-leverage step: a check the session can run beats a claim. Four levels, in order, each proving something the previous one cannot.

## Hard limits

- Read [eng-foundations](../eng-foundations/SKILL.md) first; cite rules by ID.
- Evidence is recorded on a clean tree after the commit; a dirty tree is refused and `close-check` rejects its evidence (ENG-EVID-1).
- A feature is never marked passing on a partial run; a level that cannot run is named with its blocker in the handoff (ENG-EVID-2).
- Fixture results and live results are reported separately; evidence is redacted before it is written and never contains key material (ENG-EVID-2, ENG-EVID-3).
- The live level touches only the sandbox (ENG-BOUND-1) and starts with the identity check.

## The four levels

| Level | Command | Proves | Needs |
|---|---|---|---|
| 1. Full gate | `uv run e-agent-harness gate full` | static checks, import contracts, the deterministic suite, OpenAPI and UI generation unchanged, UI type check, unit tests, layer and neutrality rules and build | the checkout with UI dependencies installed (`pnpm --dir ui install`) |
| 2. Postgres run | `uv run e-agent-harness gate pg` | store conformance on the durable store (ENG-STORE-1) | `E_AGENT_TEST_PG_DSN` naming a separate test database; the tests truncate it, and the gate refuses when it names the same database as the live ledger in `E_AGENT_PG_DSN` |
| 3. End to end | `make e2e` | the UI against its own fixture backend through a browser | Node, pnpm and the Playwright browser installed |
| 4. Live check | `uv run e-agent-harness live-check`, then the phase plan's live flows | identity of the sandbox, environment readiness, the configured flows with run ids, states and reason codes | the owner's machine; the [live-sandbox](../live-sandbox/SKILL.md) skill for any mutation |

Run levels 1 to 3 after every phase task where the plan asks for them, and all four at the end of a phase (roadmap rule 1). A UI-only task can use the `ui` gate set.

## Workflow

1. Confirm a clean tree: `git status --short` prints nothing. Otherwise commit first.
2. Run the levels in order. Stop at the first failure; fix through [eng-implement](../eng-implement/SKILL.md), commit, and start again at level 1.
3. Note each evidence path the harness prints (`harness/state/evidence/gates/<task>/…`, `harness/state/evidence/live/…`) and the counts; the files are committed with the bookkeeping.
4. For a level that cannot run here, write the reason in the handoff's verification section by name: which level, what was missing, who can run it.
5. Hand the evidence paths and counts to the close ritual in [eng-session](../eng-session/SKILL.md).

## Before handing off

- [ ] Every level that ran has an evidence path and its counts in the handoff.
- [ ] Every level that did not run is named with its blocker.
- [ ] No evidence file contains key material.

## Stop gate

Evidence from a dirty tree, a failed level, or an unnamed skipped level does not close a task.
