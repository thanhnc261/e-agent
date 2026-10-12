# Public model-call replays

Captured from the existing local `qwen3-coder:30b` weights under alias `e-agent-mvp-qwen3-coder-20261007:latest`, context 32768, temperature 0 and seed 0, on 2026-10-07. Each file contains accepted model tool-call parts and final public text from a fresh deterministic fixture ERP run through the real kernel and validators with labelled harness approval.

Thinking, provider metadata, incidental pre-tool text and tool-return messages are excluded. These are synthetic data and deterministic CI inputs, not live ERP, human-approval or model-reliability evidence. The replay callback proposes the recorded calls; current host authorization, facts, SHACL, approval and independent verification decide the outcome. It never replays fabricated provider results.

`apps/server/tests/test_recorded_model_replays.py` covers all eight tasks and a mutated late-orders answer that must fail verification. Failed capture attempts remain in the remediation evidence, including the first late-orders recording attempt; selecting accepted calls for regression does not remove those failures from model qualification.

To regenerate deliberately on a local machine with the pinned alias:

```bash
PYDANTIC_AI_NO_BANNER=1 uv run python scripts/capture_model_replays.py \
  --model e-agent-mvp-qwen3-coder-20261007:latest \
  --out tests/replays/erp-model-calls --evidence evidence/replay-capture
uv run pytest -q apps/server/tests/test_recorded_model_replays.py
```

A recording run is another trial of the candidate. Retain failures and recompute the consecutive-pass gate before claiming a current model checkpoint.
