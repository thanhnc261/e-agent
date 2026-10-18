# Authored plan replays

These recordings were written by hand in Task 2c.9 on 2026-10-18. No model produced them, and no live or remote model was called. Each file carries `provenance: "authored"` and claims no model digest, seed or temperature. The captured recordings in `../erp-model-calls` are a different kind and stay separate.

`draft-po-plan.json` checks the pydantic-ai driver's plan output against the real host in execution IR `on`, with a fixture budget of two writes. Its read calls copy the arguments of the captured `draft-po` recording. It then makes one `propose_plan` call with two draft POs, and the second copies `requested_date` from the first PO's verified read-back through lineage. Two orders for one demand only demonstrate lineage; this is not a procurement scenario.

A pass is evidence that the driver turns a plan call into `ProposePlan` and that the host validates, approves once, dispatches and verifies it. It is not evidence that any model can produce such a call. A captured plan recording would need a local model run like the ones `../erp-model-calls/README.md` describes.

`tests/unit/server/test_recorded_model_replays.py` replays every file here and fails on a file that it does not list.
