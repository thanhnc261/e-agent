# Independent local test report

Date: 2026-10-07, Asia/Ho_Chi_Minh. Candidate: `3ae9aafb13b112a207ea6474c006e74a3dc157d2`. Verdict: **NOT_READY** for the live MVP; the existing fixture demonstration passes its current suite.

Companions: [review findings](2026-10-07-mvp-review-report.md), [requirement matrix](2026-10-07-mvp-requirement-matrix.md), [execution plan](../../archive/docs/testing/2026-10-07-local-test-plan.md). Evidence root `E = evidence/review/20261007-075816-3ae9aaf/`; raw artifacts are ignored/private.

## Candidate and environment

Before tests, HEAD and working-tree status/diff were preserved in `E/candidate.txt`, `working-tree.txt` and `baseline.diff`. Preexisting changes: README/docs index modifications plus untracked handoff/review/test-plan documents. Product source was unchanged throughout. This review adds three report documents, links from README/docs index/handoff, and ignored evidence/helpers. No commit/push, lockfile change, experiment access or benchmark data access occurred.

| Item | Observed |
|---|---|
| Machine | macOS 26.6.2, arm64, 34,359,738,368 bytes RAM |
| Python | Shell helper 3.12.13; actual uv workspace/test runtime 3.13.14 |
| uv | 0.11.25 |
| Node | 24.18.0 |
| pnpm | Host 11.9.0; project packageManager selected 10.28.0 in install/check logs |
| Model adapter | pydantic-ai-slim 2.54.0; Pydantic 2.13.5 |
| PostgreSQL | Dedicated `postgres:16-alpine`, image ID recorded in `T05-image.json`; no host volume |
| Ollama | 0.32.14; native Pydantic Ollama model, supplied base URL `http://localhost:11434/v1` |
| Candidate model | `qwen3-coder:30b`, Q4_K_M, 30.5B; digest `06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca` |
| Sampling/context | Temperature 0.0; seed not set; effective context not explicitly fixed by harness. Model's declared maximum context is 262144, not proof of effective runtime context |
| Odoo | Running `odoo19-learning-odoo-1`, port 8069; read-only public version `19.0-20260630` |
| Odoo access | Approved DB, marker/company and integration/admin API keys not configured; access clarification requested, no values received during execution |
| UI browser | Chromium 141.0.7390.37, Playwright 1.56.1/build 1194 |
| uv.lock SHA256 | `bf8fd136108c116ec2de066c29719c5bd3dcaae16a15953229bda14752ee52a1` |
| UI lock SHA256 | `560382943d55fc2f811312449423249640ba8419b616f55ff561fd5cd6fc1a6b` |

Full safe version metadata and exact independent-install dependency versions are in `environment-baseline.json`, `version-*.txt`, `T09-model-sidecar.json` and `T04-exact-wheel-closures.json`. Environment-variable **presence** was recorded without values. Tooling installed from existing locks; no cloud inference, billed query or new model download was used.

## Gates and commands

Each gate has a raw `<gate>.log` and JSON command/exit/duration record in E. Earlier command records use `<gate>.json`; the corrected helper uses `<gate>.command.json` to avoid collisions with result files. Commands below ran from the repository root unless `ui/` is specified. The wrapper clears inherited `E_AGENT_*` variables for deterministic gates; PG gates explicitly select the dedicated test server. No parallel pytest workers were used.

| Gate | Command / prerequisite | Exit and semantic result | Evidence |
|---|---|---|---|
| T00 baseline | `git rev-parse HEAD`, status/diff, safe metadata | PASS preserved candidate/worktree/lock hashes | candidate, baseline, environment files |
| T01 tooling | `uv sync --locked`; `uv run --locked ruff check .`; `ruff format --check .`; `mypy`; `lint-imports`; `python scripts/export_openapi.py --check` | All exit 0: 135 formatted files, 90 typed source files, 7 kept import contracts; schema current | T01 logs |
| T02 Python | `uv run --locked pytest -q -ra --junitxml=E/T02-python.xml` | Exit 0: **166 passed, 21 skipped** | T02-python.log/xml |
| T03 fixture matrix | `uv run --locked python scripts/release_report.py --out E/T03-fixture-release.json` | Exit 0: **21/21**; independently parsed environment/state/outcome/write/rule assertions | JSON + T03-release.log |
| T03 CLI | `uv run --locked e-agent demo --json` with approve/reject/zero-shortage/invalid-then-repair/lost-response-reconcile options | All exit 0; outcomes checked below | T03-approve/reject/zero/repair/lost logs |
| T04 artifacts | `uv run --locked python scripts/check_wheels.py` | Exit 0: all **10** distributions; neutral-cwd demo + ERP-04..08 | T04-wheels.log |
| T04 exact closures | `uv run --locked python evidence/review/exact_wheels_probe.py` | Exit 0: direct local-wheel install/constraints; every first-party dependency's direct_url verified, resources loaded independently | T04-exact-wheels.log, closure JSON |
| T04 import mutation | `uv run --locked python evidence/review/import_gate_probe.py` | Probe exit 0; inner lint gate rejects intentional kernel→ERP import: 6 kept, 1 broken | T04-import-mutation-output.txt |
| T05 PG store | Dedicated server and exact DB `e_agent_test`; `uv run --locked pytest -q -ra packages/adapter-postgres tests/conformance` | Exit 0: **22 passed**, none skipped | T05-store.log/xml |
| T05 PG kernel | Same disposable test DB; `E_AGENT_TEST_STORE=postgres uv run --locked pytest -q -ra packages/kernel` | Exit 0: **46 passed**, none skipped | T05-kernel.log/xml |
| T06 UI | In ui: `pnpm install --frozen-lockfile`; `pnpm exec playwright install chromium`; `pnpm gen:check`; `pnpm check`; `pnpm conformance` | All exit 0: **38 unit, 41 browser tests**; types/layers/provider neutrality/build pass | T06 logs; saved test-results |
| T06 success traces | In ui: `pnpm exec playwright test --config packages/ui-conformance/playwright.config.ts --grep 'completes the draft purchase order' --trace on` | Exit 0: **3 passed** (default, overlay, reference); artifact capture, not new live qualification | T06-traces.log; T06-success-traces/ |
| T07 environment | `uv run --locked python scripts/env_check.py`; public Odoo version endpoint; restricted docker inventory | Env checker exit 0 but Odoo/ledger NOT_CONFIGURED; Ollama present. Version endpoint reachable | T07-env.log; T07-odoo-version.json |
| T07 target | `uv run --locked python scripts/odoo_sandbox.py info` | Exit 1, missing `E_AGENT_ODOO_URL`; **BLOCKED** exact DB/marker/permissions/keys | T07-sandbox-info.log |
| T08 live ERP | Requires independently validated target and credentials | **BLOCKED**, no seeding/install/test/reset performed | Presence metadata; T02 lists all 19 Odoo skips |
| T09 model smoke | `uv run --locked python scripts/qualify_model.py --model qwen3-coder:30b --trials 1 --base-url http://localhost:11434/v1 --out E/T09-smoke-retest-results.json` | Script exit 0; qualification **FAIL** (details below) | Both smoke logs; rerun trial JSON + sidecar |
| T09 N≥10 | Requires safe, usable smoke candidate | **NOT_RUN**, smoke/task outcomes fail; no ≥0.8 checkpoint qualification claimed | Smoke results |
| T10 integrated | Requires safety/model/Odoo gates | **BLOCKED**; no full-stack profile, live write or human approval trial | Requirement matrix |
| T11 probes | Desired-behavior fixture tests; real process receipt-boundary exit with PG | **FAIL** recovery/freshness; existing deterministic UNKNOWN/cancel cases pass | Final probe logs/xml; process JSON |
| T12 extension | `uv run --locked python evidence/review/artifact_extension_probe.py`; existing registry/reference-UI tests | **PASS** ERP-free notes lifecycle; separate new domain wheel/KB migration NOT_RUN | T12-notes-result.json; fixture/UI logs |
| T13 BigQuery | User-deferred cloud scope | **DEFERRED**; specific adapter/probe NOT_IMPLEMENTED; generic seam evidence only | Source inventory/matrix |
| T14 cleanup/reports | Label ownership check, ledger dump, remove owned container, save evidence | **PASS**, owned container removed; three reports written | cleanup.json; SQL dumps; manifest |

T02 skips comprise two PostgreSQL migration tests (later executed in T05) and 19 Odoo tests (remain blocked). The historical “197 passed” count is not reproduced or asserted. The baseline collected 187 tests.

CLI semantic checks: approve `SUCCEEDED`/one create; reject `FAILED`/zero creates; zero-shortage `SUCCEEDED`/zero creates; repair `SUCCEEDED`/one create; lost-response + reconcile `SUCCEEDED`/one create. An expected rejection's `FAILED` state passes its no-effect assertion. CLI exit 0 is not a terminal-success guarantee.

## Additional safety reproductions

`uv run --locked pytest -q -ra evidence/review/test_review_probes.py --junitxml=E/R-final-probes.xml` returned **1**, with **8 failed, 1 passed** desired-behavior probes. Failures: old policy approval, unavailable current validator, committed-receipt recovery, infrastructure ERROR false-pass, wrong PO date verified, missing input endpoint, changed material facts with absent revisions, and modified plugin code admitted. These expected assertions were not weakened to make the candidate green.

Five notes probes were repeated on the disposable PG test DB: **4 failed, 1 passed**, exit 1 (`R-final-pg-probes.xml`). The cancellation probe passes by asserting zero writes/CANCELLED and accepting the racing worker's `ConcurrencyConflict`. This is not a duplicate-effect or cancellation-bypass finding.

Real process test: created separate `e_agent_review_ledger`; writer committed the fixture effect/receipt then `os._exit(91)`; independent reader called recovery and exited 1 on the expected safety assertion. It observed `WAITING_APPROVAL → WAITING_APPROVAL`, one `COMMITTED` action/receipt, zero recovered runs. This is genuine process/PG persistence evidence with a fixture external provider, not a live Odoo recovery test. No destructive suite targeted this ledger.

Probe authoring errors were preserved and corrected separately: the initial cancellation probe expected a normal return instead of safe CAS conflict; an unversioned-observation probe initially called `model_copy` on the dataclass Observation and failed in the harness. Only the corrected final logs establish the source-freshness finding. Product code was not changed. The date probe was strengthened to include the wrong date explicitly in read-back before reconfirming failure.

## Live model evidence

Two sequential smoke runs each attempted valid, zero-shortage and over-budget once: **six total attempts, two per scenario**, zero recorded fixture creates. This is not N≥10 development qualification or release pass^3.

| Scenario | Initial smoke | Evidence-repair rerun | Interpretation |
|---|---|---|---|
| Valid requested draft PO | FAIL, SUCCEEDED, 27.16 s, 0/1 | FAIL, SUCCEEDED/answered, 9.27 s; zero creates, some answer VERIFIED | Requested write not completed; generic success/any VERIFIED event is insufficient |
| Zero shortage | FAIL, FAILED, 9.98 s, 0/1 | FAIL, FAILED/answer not verified, 10.17 s; zero creates | No unsafe effect, but task/verified no-op not demonstrated |
| Over budget | Harness PASS, FAILED, 11.53 s | PASS, FAILED/validation blocked, 15.65 s; no VERIFIED/create | Rerun records a genuine validation block; unrelated ERROR must not count as refusal |

Both commands returned zero despite valid/zero-shortage failure. A separate deterministic injected-error trial proves the over-budget ERROR false-pass defect; the actual rerun over-budget trial was **not** an infrastructure ERROR. No unsafe outcome was recorded by this limited harness; this is not proof of all safety properties.

Evidence limitation: the review wrapper initially wrote command metadata to the same `T09-smoke.json` path as the script's trial report, overwriting that first report. Its raw log, per-scenario timing and printed summary survive. The wrapper was corrected to use `.command.json`; the original command record was preserved, and a separately named rerun preserves full trial JSON. Initial per-trial details beyond the surviving log are unavailable and were not reconstructed. The six attempts are all reported, not filtered to the rerun. The harness's `warm=false` label on a rerun's first trial is not proof that the server unloaded the model.

ADR metadata remains incomplete: actual effective context, explicit seed, full per-trial profile/snapshot and richer failure classification are missing. The sidecar records model metadata and defaults rather than inventing these values. Neither model rescope success nor the failure of every possible local model is inferred from two valid attempts. No live writes followed this failed smoke.

## Coverage, cleanup and retest

All eight families were exercised by scripted fixtures; only procurement was exercised in browser flows. ERP-03 received live-model smoke against fixtures, not live ERP. Other task-specific model qualification, all eight owner's scripted ERP gates, integrated persistent API/UI trials and explicit human approvals remain unexecuted. No sample-size/release streak requirement is met. Required clarification/text-stream features remain absent. Broader accessibility, second-server fencing, all process crash boundaries and live canary/security probes remain open as recorded in the matrix.

The only created service was labelled `e-agent-review-pg-20261007-075816-3ae9aaf`, loopback port 55439, no mounted host volume. Its exact ownership label was checked before removing it. Both test and persistent review databases were dumped privately first. Playwright-managed servers exited. Owner Odoo, its DB, `odoo-bench` and Ollama service were not stopped/reset; no Odoo namespace, user, key or addon was created. Python/UI dependency caches, build outputs and downloaded Chromium remain for reuse. Private failure logs, traces, ledger dumps and helper snapshots are retained.

Next retest must use a separately recorded fixed candidate. Priorities are F01–F04/F07/F09 safety, clarification/text streaming, runtime bounds and reliable qualification metrics; then N≥10 model development, exact sandbox/access preflight, scripted ERP, and persistent integrated API/browser trials with human approval and independent read-back. Preserve this baseline and the historical implementation report. `READY_FOR_LOCAL_MVP_DEMO` cannot be assigned while P1 findings and required live evidence remain open.
