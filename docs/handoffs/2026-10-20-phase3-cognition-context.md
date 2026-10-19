# Phase 3: cognition and context (2026-10-20)

## Summary

- **Plan:** [Phase 3 plan](../plans/2026-10-19-phase3-cognition-context.md), Parts 3a to 3g; [roadmap](../roadmap.md) row 3; [ADR 0030](../adr/0030-data-governance.md) (Phase 3 parts), [ADR 0031](../adr/0031-progress-ledger-and-reconstruction.md), [ADR 0032](../adr/0032-context-assembler.md) and [ADR 0033](../adr/0033-explanation-and-grounded-answers.md), accepted at gate G2 on 2026-10-19.
- **Branch:** `phase3/cognition-context`, cut from `main` at `3ec2d70` (Phase 2 merged). Not pushed and not merged.
- **Execution:** the development harness ran every task, 3a.1 to 3f.2 and the phase-review fix 3.R1, through contract, `check-scope`, gate evidence on a clean commit, feature flip, handoff and `close-check`. Review records are in `harness/state/3/reviews/`. The whole-phase review ran in a fresh Claude context (`3g.1-phase.json`, seven findings, below).
- **Result:** behind three profile toggles, all `off` by default and `off` in every committed profile:
  - `features.context_assembler`: the kernel builds a budgeted, masked and fenced context pack for each driver call, and the driver renders it in `on`;
  - `features.kernel_repeat`: a repeated validation-blocked write proposal gets `KERNEL-REPEAT` without a second validation;
  - `features.grounded_answers`: citations and rationale checked against this run's evidence and the rule inventory, and the generic `grounded.answer.v1`, which ends `GROUNDED`, never `verified`.

  Without a toggle, because they change no run: the progress ledger, run reconstruction from `run_events` and the explanation projection (`e-agent explain`, the bundle's `explanation` key). The ADR 0030 startup rule and the per-call route check also have no toggle.
- **Evidence:** all of it is fixture evidence (simulator, scripted and authored drivers, memory and test Postgres stores). The live check 3g.2 has not run. A Codex final check is deferred until after 2026-10-25 (Codex quota).

## What changed

| Task | Commits | Content |
|---|---|---|
| plan | `29b0a43`, `74d7070`, `271d4b5`, `e3f8df4`, `8336329` | Phase 3 plan, reviewed (`3-plan.json`) and approved by the owner with every default (D1–D10) |
| 3a.1 | `bc0eaa6`, `e5f32a0`, `f47bf28` | ADRs 0031, 0032 and 0033 written; ADR 0030 amended (loopback rule, boundary basis, `data_classes` beside the schema). Docs only |
| 3a.2 | `1c1bde4`, `659fa3b` | Gate G2: the owner accepted the ADRs, including digest-only rationale storage; plan amended |
| 3b.1 | `4648bfe`, `e9b790d` | Model route data boundary and the startup rule; readiness and the bundle report `data_boundary`, `data_boundary_basis`, `data_processing_declared` |
| 3b.2 | `58a5663`, `ba3819b` | ERP `off` model-request golden; the three toggles; eight reason codes; `context.failed`; modes pinned per run; per-call route check (`ROUTE_BOUNDARY_UNMET`) |
| 3b.3 | `f5cd4b6`, `5c5ed0c`, `e891799`, `bcc4829`, `cbeaa4e`, `4f21f71` | Data classes keyed by instance path (owner decision), 12 stored record kinds, 13 ERP read output schemas, readiness `unmarked_properties`, `sdk_api` 1.2 |
| 3c.1 | `9badeff`, `10ea53c`, `427ed96` | Progress ledger projection (`kernel/progress.py`) |
| 3c.2 | `dee7802`, `cb5c11d`, `5951eac` | Run reconstruction from `run_events` (U3); additive event keys; v3 goldens beside the frozen Phase 2 goldens, with a projection test |
| 3c.3 | `d1e767f`, `de94270`, `d4b67f8` | Deterministic explanation projection (Q5, G11); bundle key `explanation`; `e-agent explain <run_id>` |
| 3d.1 | `56bce7a`, `d5e7000` | Context contracts (`ContextPolicy`, `ContextPack`, `RenderedObservation`); `DriverInput.context` |
| 3d.2 | `c235951`, `4331c08` | The pure assembler: layer budgets, drop log, bounding, clearing, class-per-route masking, fencing |
| 3d.3 | `b1ddb93`, `94b8010`, `3dae1aa` | `context_assembler: shadow` (`context.compared`); release-report context columns; first `phase3-baseline.json` |
| 3d.4 | `03516a6` | The pydantic-ai driver renders the pack (target §7.4); `rendering: "pack"` in the snapshot of a pack-rendered run only |
| 3d.5 | `6379337`, `2cccc2f`, `d042b33`, `4b79662`, `dbedf0e`, `b5cf235`, `f821e46` | `context_assembler: on` in the kernel: reservation-aware fallback, loosest-boundary rule, `context.assembled`, restore check before a driver turn (`DRIVER_STATE_MISMATCH`) |
| 3d.6 | `a713cb0`, `9e3787f` | `KERNEL-REPEAT` behind `kernel_repeat` (`kernel/repeat.py`); `repeat.compared`; release-report repeat columns |
| 3e.1 | `3ce4e36`, `6eba333`, `46bb146` | Checked citations on typed answers (`kernel/grounding.py`); `KERNEL-CITATION`; at rest only evidence id, pointer and value digest |
| 3e.2 | `51872b0`, `7726ad2`, `861394d`, `c5db618`, `8002b77`, `bb818dd` | `grounded.answer.v1` and `ReasonCode.GROUNDED`; `AcceptanceSpec.grounded_answer`; ERP read-only task `open-pos`; UI labels "grounded, not verified" |
| 3e.3 | `6414dca`, `7bd8b77`, `5cf3563` | `ProposalRationale` on proposals and plans (`kernel/rationale.py`); `KERNEL-RATIONALE`; `PluginContribution.rule_inventory` seam |
| 3e.4 | `9ca5244`, `433e641`, `f9e2f03` | `DriverInput.grounding`; the pydantic-ai and procurement scripted drivers emit citations and rationale; authored grounded replays; shadow consumer |
| 3f.1 | `4944e07`, `fedd8e2`, `224b419` | Driver conformance suite (28 cases) over the pydantic-ai and scripted ERP drivers |
| 3f.2 | `aa14ce3`, `fd5d820`, `c33feb2`, `b5e8b7a` | Context ablation design and first fixture run; repair-rate metric redefined on the kernel's repair counter; baseline regenerated |
| 3.R1 | `24d6878`, `ad927be`, `f243991` | Phase review P-1 and P-2: model-authored refs are stored as written only when they name something real, else as digests; citation length caps |
| 3g.1 | this commit | README, roadmap status, regenerated `evals/reports/fixture-release.json`, this handoff |

Task-level detail, rulings and evidence: `harness/state/3/handoffs/*.json` and `harness/state/3/reviews/*.json`.

## What was verified

Every task's own gates passed on a clean commit: `full` for 3a.1, 3a.2 and 3b.1, and `full` and `pg` for every later task (`harness/state/evidence/gates/<task>/`). `make e2e` passed per task in 3d.4 and 3e.4 (150 passed, 4 skipped; the logs are in session scratchpads, not committed). The 3d.5 handoff records no `make e2e` run.

End-of-phase levels 1 to 3, on a clean tree. All results are fixture evidence; none is live.

```text
# Level 1: full
uv run e-agent-harness gate full  -> ok, 2051 passed, 30 skipped (commit 4c137c4, clean tree)
harness/state/evidence/gates/3g.1/2026-10-19T23-24-55.111258+00-00-full.json

# Level 2: pg
uv run e-agent-harness gate pg    -> ok, 1160 passed on Postgres e_agent_test (commit 4c137c4, clean tree)
harness/state/evidence/gates/3g.1/2026-10-19T23-26-22.129629+00-00-pg.json

# Level 3: make e2e
make e2e                          -> exit 0, 150 passed, 4 skipped (1.4m), commit 4c137c4; log in the session scratchpad, not committed
```

### Fixture release report

`uv run python scripts/release_report.py --out evals/reports/fixture-release.json` was regenerated. It stays labelled `environment: fixture` and is not live qualification.

| | `phase3-baseline.json` at 3d.3 | `phase3-baseline.json` at 3f.2 (current) | `fixture-release.json` (this commit) |
|---|---|---|---|
| Cases | 21/21 | 21/21 | 21/21 |
| Repair rate | 0.4706 (16/34) | 0.3824 (13/34) | 0.3824 (13/34) |
| Ends | — | 17 verified, 4 failed | 17 verified, 4 failed |
| Model tokens | unknown | unknown | unknown in all 21 cases |

- The regenerated `fixture-release.json` is byte-identical to the committed `phase3-baseline.json`, so the baseline is current and was not regenerated again.
- The drop from 0.4706 to 0.3824 is a change of metric, not of behaviour: 3f.2 made the numerator the kernel's own repair counter (13 repairs; 18 accepted and 3 terminal refusals in the 34 attempts, 0 policy denials). The old 3d.3 count included every non-PASS validation (D3-31).
- The `fixture-release.json` committed before this task predates Phase 3 and has no repair or token keys, so there is no earlier fixture-report figure to compare.
- Token cost cannot be compared: the scripted driver reports no token use, so `model_tokens` is `unknown`, never 0.

Shadow variants, run once each to quote the counts (output kept in the session scratchpad, not committed). Every variant: 21/21 cases, repair rate 0.3824, same ends.

| Variant | Counts |
|---|---|
| `--context-assembler shadow` | 21 cases, 72 driver turns; pack 53216 = unbounded 53216 estimated tokens (kernel estimator, not model tokens); 0 dropped, 0 masked, 0 omitted; 0 shadow failures |
| `--kernel-repeat shadow` | 14 cases with repeat columns; 24 compared, 6 would repeat, 0 disagreements, 0 shadow failures |
| `--grounded-answers shadow` | 12 cases with grounding columns; 18 comparisons; citations 11 cited, 11 resolved; rationale evidence refs 24/24 and rule refs 40/40 resolved; 0 unresolved, 0 shadow failures |

Zero disagreements and zero unresolved refs are what the scripted driver gives. They show the host path is the same in shadow; they say nothing about a model.

`scripts/context_ablation.py` was re-run to the scratchpad: byte-identical to the committed `evals/reports/phase3-context-ablation.json` (21/21 cases with the same outcome and repairs in both arms; `on` built 72 packs, 53216 estimated tokens, 0 fallbacks, 0 drops). This is a check that the report is current, not new evidence.

Test consumers recorded in the task handoffs (fixture): `test_shadow_pack_keeps_referenced_observations` over the replay corpus (3d.3); the `kernel_repeat` corpus consumer, 22 cases, 27 compared, 8 would repeat, 0 disagreements (3d.6; a different corpus from the release report); `test_grounding_shadow_agrees_with_on`, 4 comparisons over 4 authored replays (3e.4); the driver conformance suite, pydantic-ai 28 passed, scripted 14 passed and 14 not applicable with typed reasons (3f.1).

## Phase review

The whole-phase review ran in a fresh Claude context (`harness/state/3/reviews/3g.1-phase.json`): **rework**, seven findings.

| Id | Severity | Finding | Handled |
|---|---|---|---|
| P-1 | Medium | Model-authored rationale ids (`goal_ref`, unresolved evidence and rule refs) were stored as written in events, the bundle and the explanation, and could hold values | Fixed in 3.R1 (`24d6878`, `ad927be`, `f243991`; reviews `3.R1-r1.json` rework, `3.R1-r2.json` accept) |
| P-2 | Low | `Citation.pointer` and `evidence_id` were unconstrained; an unresolved pointer was stored as written | Fixed in 3.R1: digests at rest, pointer ≤ 1024 and evidence id ≤ 128 characters |
| P-3 | Low | 3f.1 changed driver behaviour with every toggle `off`: silence after a finding parks the run in WAITING_INPUT; a token-budget pre-check | Open: owner decision (3f.1 R1-3) |
| P-4 | Low | No test pins `kernel_repeat: on` together with `grounded_answers: on` | Open |
| P-5 | Low | Kernel modules at about 500 lines, with no gate enforcing the limit | Open; `kernel/grounding.py` is at exactly 500 |
| P-6 | Low | Kernel task rounds without the Codex review the plan requires | Open; Codex final check deferred until after 2026-10-25 |
| P-7 | Low | Not reviewed: Postgres behaviour directly, `close-check`, `make e2e`, the `/health/ready` toggle report, Review Focus 2 and 3 | Open; levels 2 and 3 above cover the gate runs, not a review |

Codex reviewed 3b.2, 3b.3 (four rounds), 3d.5 (three rounds), 3e.3 (two rounds) and 3e.4 (round 1). The plan also asked for Codex on 3c.1, 3c.2, 3c.3, 3d.2, 3d.3, 3d.6, 3e.1 and 3e.2; those, 3d.5 rounds 5 and 6, 3e.4 round 2, 3f.1 and 3f.2 had Claude reviewers only, because Codex was out of quota. Two fix rounds were checked by the controller, not a fresh reviewer: 3e.4 `f9e2f03` and 3f.1 `224b419`.

## Rulings

The main rulings, each with its cost if wrong. The rest are in the task handoffs.

- **Rationale text is stored only as a digest** (owner, G2). Events, the bundle and the explanation hold ids, codes and text digests; the text lives only in the run's continuation, for the approval card. Cost if wrong: the text is gone once the continuation is; storing text is additive.
- **Data classes are keyed by instance path** (owner, 3b.3), after three Codex rounds found schema aliasing that lowered a class. Cost if wrong: a shared definition is classed at each use.
- **Numbers in observation data are rendered as canonical decimal strings**, so the pack digest stays the plain ADR 0006 digest (3d.1). Cost if wrong: the model sees `"3"` where a provider returned `3`; the owner may override with "Tag".
- **The repair budget's exact counter is the metric**: the ledger reports failed validations (3c.1), the release report reads the kernel's repair counter from the continuation (3f.2). Cost if wrong: one metric definition change.
- **A run keeps the loosest route boundary it used and refuses a stricter one** (3d.5). Cost if wrong: a run whose route tightens fails instead of continuing.
- **Driver state is restored only before a driver turn**; kernel-only paths never restore (3d.5, ADR 0032 §8 amended, owner acceptance pending). Cost if wrong: a mismatch is found at the first driver turn, not on load.
- **With `context_assembler` on, a citation resolves only against what the pack showed the model**; masked, removed or reduced values are UNRESOLVED (3e.1). Cost if wrong: one repair for a legitimate citation on a masked value, never a leak.
- **`open-pos` uses existing reads** and stays a preset for the live driver; the scripted driver refuses it (3e.2). Cost if wrong: the live question is reworded or a capability task is added.
- **The UI mislabel of a grounded run as verified was fixed as a PR-19 correctness fix**, labels and tone only, without an `ag-*` stage (3e.2). Cost if wrong: a wording change after an `ag-*` review.
- **Unresolved refs stay repairs, not refusals**; only the at-rest form changed (3.R1). Cost if wrong: a later contract tightening.

## Not implemented or not proven

- **Recordings are authored, not captured.** The replay corpora, the 3e.4 grounded replays (`tests/replays/erp-authored-grounded-calls/`) and the 3f.1 `driver_cases` responses were written by hand, because no qualified model run exists (ADR 0010, PR-29). They are fixture input, not model evidence.
- **Context token counts in shadow are kernel estimates**, not model-reported tokens. The scripted driver reports no tokens, so token cost between `off` and `on` is not measured.
- **A `GROUNDED` end is not verified** (PR-19). It means every citation resolved against this run's recorded evidence; no typed verifier read anything back. Free text outside the citations is labelled `unverified`.
- **No UI for citations, rationale or the explanation** (D10). They are exposed through the evidence bundle and the CLI only. The approval card does not show the rationale.
- **Rationale text is stored only as a digest** at rest (above).
- **No model benefit is shown.** The ablation (3f.2) shows only that `on` keeps the host safety path; the scripted driver ignores its context. Hypothesis H2 needs a qualified model run.
- **Only the procurement scripted driver offers rationale and citations.** amend-rfq, quotation, crm-lead, late-orders and overdue-invoices show zero or null in the grounding columns.
- **T1 injection** is proven kernel-side with a scripted driver only, not against a live model (3d.5).
- **Driver state at rest is not minimised.** The pydantic-ai driver's stored message history holds each raw finding's observed value and the model's own tool arguments as written (parked from 3.R1).
- **Events recorded before `24d6878`** keep their refs as written; there is no migration (pre-merge branch data only).
- **Other gaps named in task handoffs:** restore errors other than the rendering mismatch still raise an uncaught `ValueError` (3a.1); `driver_turns` and `model_tokens` in the ledger stay unknown (3c.1); the post-reservation repeat path is tested white-box only (3d.6); a malformed citations or rationale field becomes a clarification turn and may stall a live run (3e.4); the CLI shows the scripted refusal of `open-pos` as an uncaught `ValueError`, not `STARTUP_REJECTED` (3e.2 R2-4); the repair rate overstates on two paths the corpus does not reach (3f.2 R3-1, R3-2).
- **Not done:** levels 3 and 4 as phase-end evidence are the `make e2e` result above and the live check 3g.2, which has not run.

## Owner decisions and ADR amendments pending

Design and ADR text is the owner's to amend; this task changed none of it.

1. **target-architecture.md**
   - :319 says no rationale field exists; now false (`ProposalRationale`, `Citation`, at-rest rationale, the bundle's `explanation` key).
   - :548 marks repeat detection `[P]` and cites `kernel/proposals.py:303-314` for `_handle_answer`; it is now in `kernel/grounding.py` and `kernel/repeat.py`. :1199 has the same stale ref (3e.1).
   - Re-tag what was built behind toggles: §5.1 item 2 reconstruction (:317), §5.6 explanation projection (:471), §7 ContextAssembler (:714), fitness rows U3 `[Pa]`, U6 `[P]`, Q5 `[Pa]`, G11.
   - :451 still describes the `#acceptance-item` suffix and the old at-rest form (3.R1 R1-3).
2. **ADR 0031**
   - Line 20 and Consequences :119 put the repeat rule in `proposals.py`; it is in `repeat.py`. `BlockedRevision` also keeps findings, beyond §5's wording (3d.6 R1-5).
   - File:line refs at :10, :74-78 and :101 are pre-change.
   - `rule_bundle_version` is in no event payload, so the explanation cannot name it: **Add or Skip** a §3 key (3c.3 C3-27).
   - `budgets_used` means failed validations, not the repair counter (3c.1).
3. **ADR 0033**
   - The CQ06 row (line 84) lists expected/observed, which §6 and the code exclude (3c.3 C3-28).
   - §1 "the value at the pointer" means the class-walked view when `context_assembler` is on (3e.1).
   - §4 and ADR 0009: the `PluginContribution.rule_inventory` seam, and that the record refuses non-id-shaped refs (3e.3).
   - The value digest is unsalted, so short values can be guessed offline from stored digests (3e.1).
   - §4 (lines 49, 59): `goal_ref` is kept as written only for `run` or `task_id@task_version`, else `goal_ref_digest`; unresolved rationale refs go to `unresolved_*_digests`; an unresolved citation stores `evidence_id_digest` and `pointer_digest`; pointer ≤ 1024 and evidence id ≤ 128 characters (3.R1).
4. **ADR 0032**
   - Accept the 3d.5 amendments: §8 restore check before a driver turn; §11 `context.assembled` and the `DRIVER_STATE_MISMATCH` cell.
   - Reconcile the `context.failed` turn encoding (`turn: "acknowledgement"`) with the shadow events' `turn: int` plus `acknowledgement: bool` (D3-33).
   - `rule_texts` cannot reach the kernel without a plugin import, so validator messages stay masked on undeclared hosted routes (3d.4).
5. **ADR 0006 / 0032:** observation numbers rendered as canonical decimal strings (3d.1); the owner may override with "Tag".
6. **ADR 0030:** the line-3 status still says "At gate G2 the owner accepts or amends"; a schema property named `items` is always at least `personal` (3d.5).
7. **principles.md:** the PR-34 backlog row still lists the injection outcome test as Phase 3 Task 3d.5; it landed (scripted driver only).
8. **`sdk/__init__.py`:** check that the `SDK_API_VERSION` 1.2 docstring names `PluginContribution.rule_inventory` as well as context and grounding.
9. **3f.1 R1-3 (P-3):** in every rollout, `off` included, a reasoning-only reply after a finding now parks the run in WAITING_INPUT with "The model made no usable tool request." Keep it, or prefer a bounded model retry.
10. **Driver state at rest:** whether the pydantic-ai stored message history is minimised (ADR 0032 / 0030; parked from 3.R1).
11. **`open-pos`:** no agent-visible read lists purchase orders. Add a capability and Odoo binding, or reword the live question (3e.2).
12. **`open-pos` goldens:** it is special-cased in the ERP catalog golden check and `BASELINE_PROMPTS` rather than added to the goldens (additive if wanted; 3e.2).
13. **UI wording** "Completed · grounded, not verified" (en, vi) has had no `ag-*` review (3e.2).

## Before the live check 3g.2

1. A local profile whose model route is not a loopback Ollama now needs `driver.data_boundary` or `data_processing` to start (3b.1). The agent cannot read `profiles/*.local.json` to check.
2. Renew `artifact_sha256` for `domain-erp` in the live profile pin (3b.3, 3e.2). Built twice at `7b24f00` from the wheels with `uv build --package e-agent-domain-erp --wheel` and `scripts/plugin_inventory.py`, with the same result:

   | Plugin | `artifact_sha256` |
   |---|---|
   | `domain-erp` | `0067b787dde0b4d88b135754a1f03d8e7fc726f87b3a9d9d4a47181ab2c6c860` (changed) |
   | `odoo19` | `5976460ec47f273d9136c526c1e51dcc1af06988bc4331778ef62cd5d76c09e0` (same as Phase 2) |

   The pins change only if a later commit touches `src/e_agent/plugins/erp/**`.
3. `open-pos` has no list-POs read: decide the capability or the wording (decision 11 above). The run needs `execution_ir: on`, `grounded_answers: on` and `--task open-pos` with the live driver.
4. There is no runbook entry for a run in NEEDS_RECONCILIATION with a driver-state mismatch (3d.5). After resolution the acknowledgement turn is skipped.
5. The live check's toggle settings (`context_assembler` `off`, `shadow`, `on`; `grounded_answers: on`) need profiles that set them; Phase 2 used temporary `*.local.json` copies, deleted after the check.

## Incidents

- During the 3e.3 first fix round an implementer's grep printed two `artifact_sha256` digest lines (no secrets) from `profiles/live-odoo19-learning.local.json`. The file was not opened. Later dispatches pass `--exclude='*.local.json'` to every grep.

## Changes outside the repository

| Change | Undo |
|---|---|
| The `pg` runs and the pinning tests used only the `e_agent_test` database in `e-agent-ledger` | none needed; test data only |
