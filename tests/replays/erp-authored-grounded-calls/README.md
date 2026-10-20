# Authored grounded replays

These recordings were written by hand in Task 3e.4 on 2026-10-20. No model produced them, and no live or remote model was called. Each file carries `provenance: "authored"` and claims no model digest, seed or temperature. Its `pydantic_ai_version` names the message-part format the file is written in, not a capture. The captured recordings in `../erp-model-calls` and the authored plan recordings in `../erp-authored-plan-calls` are different kinds and stay separate.

Each file checks the pydantic-ai driver's grounding envelope (ADR 0033 §5) against the real host on the fixture profile with `grounded_answers` pinned `on`: citations beside a typed answer, a rationale beside a write, and the generic grounded answer `grounded.answer.v1`. The read calls copy the arguments of the captured `shortage` and `draft-po` recordings.

Evidence ids are assigned by the host at run time, so a file names the evidence of one of its own read calls as `<<evidence:CALL_ID>>`. The replay replaces it with the `evidence_id` of that call's tool return before the driver sees the call. Nothing else in a response is changed.

| File | What it checks | Ends |
|---|---|---|
| `shortage-cited.json` | a typed answer whose three citations resolve | `answered` (verified answer) |
| `shortage-miscited.json` | a mismatched citation: `KERNEL-CITATION` in `on`, then a corrected answer | `answered` (verified answer) |
| `draft-po-rationale.json` | a write whose rationale names three reads and two inventory rules | `verified` (verified write) |
| `draft-po-misruled.json` | a rationale naming a rule outside the inventory: `KERNEL-RATIONALE` in `on`, then a corrected write | `verified` (verified write) |
| `open-pos-grounded.json` | the generic grounded answer on the bound `open-pos` task (execution IR `on`) | `grounded` |

Files with `shadow_compared: true` are also replayed with `grounded_answers` pinned `shadow`. `test_grounding_shadow_agrees_with_on` asserts that the shadow run's `grounding.compared` verdicts equal what `on` decided, up to the first check `on` refused (after it the runs diverge by design: `on` repairs, `shadow` acts on nothing). `shadow` never offers the generic answer, so `open-pos-grounded.json` is replayed in `on` only.

A pass is evidence that the driver offers and parses the envelope and that the host checks it. It is not evidence that any model produces correct citations or rationales. A captured grounded recording would need a local model run like the ones `../erp-model-calls/README.md` describes.

`tests/unit/server/test_recorded_model_replays.py` replays every file here and fails on a file that it does not list.
