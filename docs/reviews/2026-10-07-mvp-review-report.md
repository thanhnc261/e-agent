# Independent MVP review

Date: 2026-10-07. Candidate: `3ae9aafb13b112a207ea6474c006e74a3dc157d2`. Verdict: **NOT_READY** for the local model + Odoo + UI MVP.

This review executed the [handoff](../handoffs/2026-10-07-sol-6.1-mvp-review.md), [review plan](2026-10-07-mvp-review-plan.md) and independent portions of the [local test plan](../../archive/docs/testing/2026-10-07-local-test-plan.md). See the [test report](2026-10-07-local-test-report.md) for commands, environment, failures and cleanup, and the [requirement matrix](2026-10-07-mvp-requirement-matrix.md) for coverage. Historical implementation results were not counted as new evidence.

## Result

The existing deterministic gates pass: 166 Python tests, 21 fixture release cases, 22 PostgreSQL store/migration tests, 46 kernel tests on PostgreSQL, 38 UI unit tests and 41 browser conformance tests. All ten distributions install independently; an additional exact-wheel check records dependency closure and verifies local wheel origins. The notes lifecycle succeeds outside the workspace without ERP/Odoo installed, and an intentionally forbidden import is rejected in a disposable copy.

Additional adversarial probes expose failures outside those suites: policy changes and unversioned source changes do not invalidate approval, a committed receipt can be stranded after a real process exit, and a PO with the wrong requested date is falsely verified. Clarification cannot resume through the API, model text deltas are absent, and plugin admission checks manifest bytes rather than installed code integrity.

Live Ollama smoke also fails the requested draft-PO and zero-shortage cases. Odoo learning is running, but its approved database and private integration/admin credentials were not supplied in this execution. No Odoo mutation or live business-data read occurred. Full-stack qualification is blocked by both access and failed safety/model prerequisites. BigQuery-specific work remains deferred and is not a prerequisite for completing independent Odoo review work.

Raw evidence: `evidence/review/20261007-075816-3ae9aaf/` (ignored, private). Reproductions: `evidence/review/test_review_probes.py`; final logs/JUnit: `R-final-probes.*`, `R-final-pg-probes.*`; actual process failure: `T11-process-result.json`. Commands for reproducing the probes are in the test report. All findings below apply to the candidate above; no implementation fixes or commits were made.

## Findings

### F01 — P1, confirmed: policy version changes leave old approval usable

Source: [coordinator.py](../../src/e_agent/kernel/coordinator.py), `_staleness` line 810 and `decide` line 693. Requirement: MVP design §5 binds policy version into the digest and requires changed policy to invalidate eligibility.

Trigger: prepare an approval under `policy-mvp-1`, change the trusted policy to `policy-mvp-2` while retaining permission, then approve the original digest. Expected: fresh proposal/approval, zero dispatch. Observed: one fixture create and successful completion. Reproduced with memory and PostgreSQL in `test_policy_version_change_requires_new_approval`.

Remedy: compare the current policy version with the canonical approved policy version before reservation, recompute eligibility under current policy and require a new approval on drift. Regression: the same probe with zero effects and a stale/reapproval result, including process restart under a new policy version.

### F02 — P1, confirmed: absent revisions are treated as proof of unchanged facts

Source: [coordinator.py](../../src/e_agent/kernel/coordinator.py), lines 813–819; [executor.py](../../src/e_agent/adapters/odoo/executor.py), pricing/contact/team reads. Requirement: MVP design §5 compares provider revisions **or a canonical relevant-fact digest**; unknown facts must remain explicit.

Trigger: initial and refreshed observations both have `revision=None`, but refreshed material content differs. Expected: detect the change or fail closed when identity cannot be established. Observed: equality of `None` values permits one write. `test_missing_source_revision_uses_material_fact_digest` reproduces this with both stores. Several live Odoo observations have no revision, so this is not only a fixture contract edge case; exact ERP impact awaits live tests.

Remedy: derive stable material-fact digests where provider revisions are absent, retain refreshed observations, and revalidate/reapprove changes. Regression: changed pricing/contact/team facts with absent revisions, unchanged facts with new observation timestamps, and incomplete observations.

Supplementary probe: making the current validator unavailable after proposal validation still permits dispatch (`test_validator_unavailable_before_dispatch_blocks_write`, both stores). `_staleness` never invokes `_validate`. This establishes reliance on cached validation; no exposed ontology-update/admin route was demonstrated. Include rule-bundle drift and required-validator availability in the dispatch/restart regression matrix rather than claiming a live rule-publishing exploit.

### F03 — P1, confirmed: receipt commit followed by process exit strands the run

Source: [coordinator.py](../../src/e_agent/kernel/coordinator.py), `_apply_receipt` line 839 and `_recover_run` line 1052. Requirement: durable committed effects must resume independent verification without resending.

Trigger: process exits immediately after `record_receipt` commits, before the separate run transition to `VERIFYING`. Expected: recover from the committed action/receipt and resume read-only verification. Observed: action and receipt are `COMMITTED`, run remains `WAITING_APPROVAL`, and `recover()` returns no recovered runs. The existing recovery branch requires the run already to be `VERIFYING`.

Evidence: memory/PG fault probes plus a real writer process exiting with code 91, followed by a separate reader process on `e_agent_review_ledger`; `T11-process-result.json` records unchanged state and zero recovered runs. External effect is a notes fixture, not Odoo. Ledger dumps were saved before removing the disposable server.

Remedy: recover from authoritative action/receipt states across every interrupted run transition; keep the corresponding local updates atomic where required. Regression: actual process exits after receipt commit, outcome commit and before terminal completion; assert no second write and eventual verified or honestly unresolved state.

### F04 — P1, confirmed: wrong approved PO date can be VERIFIED

Source: [verifier.py](../../src/e_agent/erp/procurement/verifier.py), `DraftPurchaseOrderVerifier.verify` line 29. Requirement: exact approved material arguments and independently verified business success.

Trigger: approve the fixture PO, alter its resulting `requested_date` to `2099-01-01`, and include that actual date in independent read-back. Expected: verification failure. Observed: `SUCCEEDED`, reason `outcome verified`. `test_po_wrong_requested_date_cannot_be_verified` and `R06-date-readback.log` isolate this from the fixture view's own omission of requested date. The verifier compares monetary fields and parties but omits requested date.

Remedy: require and compare requested date in PO read-back; review line count, completeness and operation correlation as well. Regression: correct, incorrect and missing dates; preserve the approved date and returned date in outcome checks.

### F05 — P1, confirmed: clarification pauses a run permanently through the public API

Source: [coordinator.py](../../src/e_agent/kernel/coordinator.py), `AskClarification` branch line 243; [api.py](../../src/e_agent/server/api.py); generated OpenAPI. Requirement: MVP design §12 `POST /v1/runs/{id}/inputs` and conversational task completion.

Trigger: a deterministic driver asks which demand to use. Run reaches `WAITING_INPUT`; submit clarification with expected revision. Expected: accepted input and continuation of the same run. Observed: HTTP 404; neither an API input route nor a coordinator input/resume operation exists. Reproduction: `test_clarification_endpoint_resumes_same_run`.

Remedy: add authenticated, revision-checked input/resume and UI handling; carry safe input into the driver continuation. Regression: correct input, stale revision, wrong tenant, restart and duplicate submission.

### F06 — P1, source-observed: SSE streams run events, not incremental model text

Source: [driver.py](../../src/e_agent/adapters/pydantic_ai/driver.py), `advance` line 172; [api.py](../../src/e_agent/server/api.py), `stream` line 306; UI Messages component. Requirement: ADR 0001/I04/I08 and MVP design §4.1 transient `text.delta`.

The driver awaits `Agent.run` to finish; SSE only emits stored `run_event` records and an end event. No model-text producer/transport/consumer exists. Passing SSE replay and UI conformance therefore does not qualify the requested text stream. This absence is also disclosed in the historical qualification report, contradicting its broader feature-complete wording.

Remedy: implement safe incremental text from driver to presentation without treating it as business evidence; strip reasoning before emission. Regression: text arrives before final completion, disconnect/slow-client handling, and reasoning/secret sentinels. No live UI/model streaming success is claimed.

### F07 — P1, confirmed at the admission boundary: pinned manifest does not authenticate plugin code

Source: [registry.py](../../src/e_agent/kernel/registry.py), `_check_admissible` line 118 and `_load` line 135. Requirement: MVP design §6 checks installed contents against trusted artifact inventory before import; threat model T4 requires tampered artifacts to be rejected.

Trigger: a controlled fixture module is changed while its version, entry point and correctly pinned manifest remain unchanged. Expected: admission rejects code/content mismatch before import. Observed: altered module executes its synthetic marker side effect and is admitted. Reproduction: `test_tampered_plugin_code_is_rejected_before_import` in a temporary directory. This is a local artifact-tampering probe, not evidence that the model can modify installed packages or that a published wheel was compromised.

Remedy: bind admission to a trusted build/content inventory including code and resources, and verify it before import. Regression: changed module, ontology resource and manifest, with zero factory/module side effects on rejection. A trusted deployment-only alternative must be explicitly decided and reflected in the baseline rather than silently replacing the accepted integrity requirement.

### F08 — P2, confirmed: model qualification green exit and refusal counts can mislead

Source: [qualify_model.py](../../scripts/qualify_model.py), lines 105–115 and final exit expression. Requirement: ADR 0010 records genuine task success, refusal and infrastructure failure separately.

Live smoke and its evidence-repair rerun both report valid 0/1 and zero-shortage 0/1, yet return exit 0 because unsafe counts are zero. Separately, an injected infrastructure exception in the over-budget trial yields `state=ERROR`, `passed=true`. Reproduction: `test_infrastructure_error_is_not_over_budget_pass` uses a deterministic failing driver and performs no inference.

The harness covers three procurement scenarios, issues automatic approvals, lacks complete context/seed/profile metadata and does not enforce N≥10 in `rescope_checkpoint_met`. It is not eight-task, human-approval or release qualification.

Remedy: explicit business-refusal outcomes, failure classification, complete metadata and separate smoke/development/release gates with meaningful exit status. Regression: ERROR, task mismatch, empty/undersized samples, no effect on a requested write and unsafe outcome.

### F09 — P1, source-observed: sandbox identity is checked at startup, not each write

Source: [bootstrap.py](../../src/e_agent/server/bootstrap.py), `_check_sandbox` line 251; [executor.py](../../src/e_agent/adapters/odoo/executor.py), `execute`; bridge `_check` and `_require_sandbox`. Requirement: threat model T14 says exact sandbox identity/target is checked at startup and before each write.

Startup compares an expected marker. Runtime dispatch does not repeat it; ordinary bridge commands only check integration-group membership. Admin seed/reset require merely a nonempty marker, and live test fixtures seed before runtime validation. URL/DB/company target allowlisting is not established by a port suffix guard or a configurable marker alone. No marker-removal, wrong-target or company-permission attack was run on the owner's ERP; this is a source-level gap, not a claimed live breach.

Remedy: enforce exact configured target/marker/company at the authorized write boundary and independently preflight mutation fixtures. Regression: marker removed/changed after startup, mismatched company/DB and denied seed before any effect.

### F10 — P2, source-observed: runtime bounds and worker ownership differ from accepted design

Source: [context.py](../../src/e_agent/contracts/context.py), `Budgets`; coordinator `_drive`; driver `UsageLimits`; [store.py](../../src/e_agent/adapters/postgres/store.py), `writer_lock` line 367; migration SQL. Requirements: MVP design §9–10 and ADR 0003.

Turn/read/repair/write budgets exist, but there is no cumulative active-time/token budget, assigned model deadline or enforcement of `TaskContext.deadline`. The review's outer 600-second timeout is a measurement safeguard, not application enforcement. Request-count limits do not bound a single long model call.

There is also no persisted `run_work`, lease or fencing token. API run locks are process-local; PostgreSQL supplies a session-level connection writer lock. Existing writer-lock conformance passes, but it does not establish safe second-server startup/recovery or the accepted worker scheduler. No split-brain business effect is claimed.

Remedy: implement the required bounded calls/ownership checks, or use an ADR to explicitly narrow the MVP to one enforced process. Regression: hung model/read, cumulative budget exhaustion, stop during an active turn, concurrent server startup and stale-worker state commits.

### F11 — P2, source-observed: CLI task routing and the live example do not qualify eight model tasks

Source: [cli.py](../../src/e_agent/server/cli.py), `DEMO_TASK` line 22; [live.example.json](../../profiles/live.example.json); `tool_specs` in bootstrap.

`--task` selects scripted runtime behavior while the natural-language task remains procurement. The live example lists only procurement bindings. Running non-procurement CLI labels with a model is not evidence that the model received the corresponding user request. Complete live profiles must be built from the admitted manifest; ambiguous multi-connection capabilities are omitted from the model surface, while kernel resolution tests establish only explicit scoped routing.

Remedy: task-specific/user-supplied CLI prompts and a documented complete profile; test natural-language requests through the API. Regression: assert the actual model prompt and exposed capabilities for each claimed task.

### F12 — P3, confirmed documentation mismatch: inventory and qualification labels conflict

README/AGENTS still say M1/no live implementation; design and threat-model headings say research-only/no mitigations. The historical release report says feature-complete despite absent clarification/text streaming and pending live gates. The implementation plan also retains older BigQuery release wording.

Remedy: reconcile implementation inventory, qualification status and the user's BigQuery-as-extension clarification. Preserve historical reports and date corrections. A status-table row marked done must not imply owner-machine or model evidence that was never collected.

## Review coverage and limits

| Work package | Newly checked | Limit |
|---|---|---|
| R01 scope/evidence | Current inventory, accepted ADRs, semantic fixture/model results | Historical live Odoo counts not reproduced |
| R02 layers/packages | 7 import contracts; mutation rejection; exact wheels; independent notes; admission tamper | F07 remains open |
| R03 host safety | Existing denied/stale/tenant tests plus policy/fact probes on both stores | No live permission-negative ERP calls |
| R04 durability | PG conformance/kernel; real receipt-boundary process exit | F03; other real process boundaries not exhausted |
| R05 Odoo | Bridge/adapter/seed/reset source; read-only server version | Approved DB/keys unavailable; no seed/install/reset |
| R06 ontology/verifier | SHACL inventory/negative tests; 21-case matrix; wrong-date read-back | F04; broader ontology effectiveness unproven |
| R07 driver | Existing deterministic tests; six live smoke attempts across two runs | No N≥10 qualification; clarification/text gaps |
| R08 API/SSE | Existing session/CSRF/idempotency/approval/replay tests; clarification probe | Explicit hostile-Origin/Host and full cross-tenant adversarial probes incomplete |
| R09 presentation | 38 unit/41 Chromium tests; three success traces across hosts | No live model/ERP browser run; no manual accessibility certification |
| R10 secrets/evidence | Existing local-store, credential and reasoning-hygiene tests; fixture exports | No live secret lifecycle or comprehensive canary scan |
| R11 extensibility | ERP-free notes lifecycle, two-connection registry tests, reference UI | No separately authored plugin wheel/KG migration/BigQuery probe |
| R12 measurement | Exit/semantic divergence and ERROR false-pass reproduction | Complete ADR trial metadata still missing |

Cancellation during the tested pre-dispatch refresh was prevented by action CAS: zero writes and `CANCELLED`, although the racing worker raises `ConcurrencyConflict`. The first probe incorrectly expected a normal return; its refinement records the safe behavior. Do not count that exception as an unauthorized-write finding.

## Next candidate

Fix approval freshness, recovery and exact outcome verification first; add regressions preserving these failures. Implement clarification and safe text streaming, enforce the accepted artifact/target/budget boundaries, and repair measurement/reporting. Then qualify a frozen local model with N≥10, obtain the approved Odoo access configuration, independently validate target/fixture ownership and run scripted ERP plus integrated PostgreSQL/API/UI trials with explicit human approval. Retain every failure and report changed SHA/configuration. The current evidence supports the existing fixture demonstration, not a ready live MVP or enterprise readiness.
