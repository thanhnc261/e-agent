# Context ablation: chat history against typed state

This is the design of the first context ablation that [research 03 §8](../../research/03-knowledge-and-cognitive-ontology.md) asks for, and a record of its first run (Task 3f.2 of the [Phase 3 plan](../../docs/plans/2026-10-19-phase3-cognition-context.md)). The run is fixture evidence. Its report is [`evals/reports/phase3-context-ablation.json`](../reports/phase3-context-ablation.json), produced by [`scripts/context_ablation.py`](../../scripts/context_ablation.py).

## Question

Research 03 §8 proposes comparing, on the same model, corpus and budget:

- (A) chat history;
- (B) typed task state plus evidence;
- (C) B plus episodic recall;
- (D) C plus a cognitive graph and controlled memory promotion.

It names the measures: resume correctness, redundant tool calls, stale-memory errors, explanation coverage, task success and cost. If D does not beat B or C by enough to pay for itself, the simple schema stays.

This ablation covers A against B only. In e-agent, the `features.context_assembler` toggle (ADR 0032) chooses between them:

- **Arm A (`off`):** the driver renders each turn from its own message history, as Phase 2 shipped.
- **Arm B (`on`):** the kernel builds a typed context pack every turn, and the driver renders that turn from the pack. The pack holds the instructions, the task, the tool set, the progress ledger (ADR 0031), the open findings and the bounded, masked evidence (target §7.4).

Arms C and D need episodic recall and memory promotion, which do not exist. They are out of scope.

## Hypotheses

Each hypothesis says what would count against it. This run can test only H0 (see "What this run cannot show").

| ID | Hypothesis | Counted against it |
|---|---|---|
| H0 | Host-path parity. Arm B changes no outcome of the host safety path: on every corpus case it reaches the same final state, reason code, outcome reports, provider writes and repairs as arm A. | Any case whose outcome or repairs differ between the arms, or that falls back or fails context assembly in arm B |
| H1 | Outcome. With a real model, arm B ends at least as many cases verified or correctly refused as arm A. | A lower verified or correct-refusal count in B over the same trials (ADR 0010: pass@1 over N trials) |
| H2 | Repair rate. Arm B sends fewer proposals back than arm A, because the open findings and the ledger state what was refused and why. | A higher repair rate in B |
| H3 | Token cost. Arm B's per-turn context is bounded, so its cost grows more slowly with turns than A's history. | Model-reported tokens per case in B at or above A's, on cases with three or more turns |
| H4 | Dropped evidence. Arm B drops or masks evidence only where the policy says to, and never drops evidence a later proposal or answer needs. | A repair, failure or wrong answer in B that traces to an observation the pack omitted, truncated or masked |

## Metrics

Every metric comes from the release report's runner and metrics (`scripts/release_report.py`, Task 3d.3). The ablation script does not measure a case itself.

| Metric | Definition | Source | This run |
|---|---|---|---|
| Outcome | Final state, reason code, outcome reports and provider write calls per case. The `ends` counts are `verified`, `grounded` and the final states (PR-19) | `run_case`, `end_class` | Both arms |
| Repair rate | (validation repairs + answer repairs) / driver proposals. A repair is a refusal the kernel sent back to the driver. A dispatch revalidation (`STALE`), a later plan step, a plain-text turn and a finish check are not repairs, and the refusal that ended the run is counted apart as `terminal_refusals` (D3-31) | `repair_metrics` | Both arms |
| Token cost | `model_tokens`: what the driver reported. `pack_tokens_estimate`: the kernel estimator's sum over a run's packs (`estimate_tokens`). It is an estimate, not model-reported tokens | `project_progress`, `context.assembled` | `model_tokens` is `unknown` in both arms; the estimate exists in B only |
| Dropped evidence | Drops in the pack's drop log, by kind; masked values (`class_route`); observations omitted from the pack | `context.assembled` (`assembled_columns`) | B only. A keeps no drop log, so these are `unknown` there |
| Parity | Cases whose outcome and repairs are equal in both arms | the report's `paired` block | Both arms |

`unknown` is never written as 0 (PR-24).

## Corpus

The corpus is the 21 cases of the release-report task matrix (`CASES` in `scripts/release_report.py`). They cover ERP-01 to ERP-08 on the fixture ERP with the scripted driver:

- verified answers, and wrong answers that fail verification and are then corrected;
- writes that are approved and verified;
- writes blocked by an ontology rule and then repaired (PR-003, AM-002, SQ-003, CL-002);
- writes blocked until the repair budget runs out (PR-004, AM-001, SQ-002);
- an approval rejection;
- two lost provider responses that are reconciled without a second write.

Each case runs once per arm, in corpus order, with `kernel_repeat` and `grounded_answers` `off`. The two runs of a case are paired by position.

## Threats to validity

- **The driver ignores its context.** The scripted driver follows a fixed script per `driver_mode`. It never reads the pack (`DriverInput.context`) and keeps no message history: it reads the full observations, findings and action result that the kernel passes in both arms (`plugins/erp/domain/testing/scripted_tasks.py`). Equal outcomes therefore follow from the design of the corpus: they show that the `on` path does not break the host path, not that typed state helps a model decide. This is the main threat, and it is why H1 to H4 stay open.
- **Small, authored corpus.** There are 21 cases, written by the project, with small observations. Nothing in the corpus reaches an evidence bound, a budget or a masked data class, so the drop columns are zero by construction.
- **Estimated tokens.** `pack_tokens_estimate` uses the kernel's estimator, not a provider tokenizer. Arm A has no comparable estimate, because the driver's history is not measured. The two arms' token costs cannot be compared from this run.
- **One trial per case.** The fixture run is deterministic, so one trial is the whole distribution. A model run needs N trials per task (ADR 0010).
- **Same host for both arms.** Both arms share the kernel, validator, policy and verifiers. The comparison isolates the context rendering, which is the intent, but a bug shared by both arms is invisible to it.

## What this run cannot show

- That typed state improves outcome, repair rate or cost for a model (H1 to H3). That needs a model run, live or from recordings captured in both modes, over N trials.
- Any token saving. `model_tokens` is `unknown` in both arms, and arm A records no estimate.
- That arm B drops only evidence nothing needs (H4). Nothing was dropped, masked or omitted on this corpus, which is a property of the corpus, not evidence about the assembler.
- Resume correctness, redundant tool calls, stale-memory errors or explanation coverage, the other measures of research 03 §8. The corpus has no resumed runs and no memory.
- Anything beyond these 21 cases, any live ERP behaviour, or any qualified-model behaviour.

## First run

The run is recorded in [`phase3-context-ablation.json`](../reports/phase3-context-ablation.json), fixture evidence.

| | Arm A (`off`, history) | Arm B (`on`, pack) |
|---|---|---|
| Cases passed | 21/21 | 21/21 |
| Ends | 17 verified, 4 failed | 17 verified, 4 failed |
| Driver proposals | 34 | 34 |
| Validation / answer repairs | 10 / 3 | 10 / 3 |
| Terminal refusals | 3 | 3 |
| Repair rate | 0.3824 | 0.3824 |
| Provider write calls | 10 | 10 |
| `model_tokens` | unknown | unknown |
| Context turns (fallbacks, failures) | unknown | 72 (0, 0) |
| Pack tokens (estimate) | unknown | 53216 |
| Dropped / masked / omitted observations | unknown | 0 / 0 / 0 |

All 21 cases had the same outcome and repairs in both arms. H0 holds on this corpus. H1 to H4 are not tested.

Regenerate the report with:

```
uv run python scripts/context_ablation.py --out evals/reports/phase3-context-ablation.json
```

Two runs give byte-identical output. The report holds no run, action or evidence id, no pack digest and no timestamp.

## Next runs

- **Model arms (H1 to H3).** Run the same corpus with a qualified local model under ADR 0010's protocol (N trials per task per arm), recording `model_tokens` per turn in both arms. Recorded responses can then become `on`-mode replays.
- **Drop pressure (H4).** Add cases whose observations exceed the capability bound, or that carry a masked data class on a hosted route, and check every later proposal against the drop log.
- **Arms C and D.** These wait for episodic recall and memory promotion, which need their own design and ADR.
