# Architecture alignment review

Date: 2026-10-07. Reviewed candidate: uncommitted working tree based on `3ae9aafb13b112a207ea6474c006e74a3dc157d2`, including approved remediation. This is a source/design review with new synthetic probes, not live Odoo qualification. Existing reports and remediation archives remain unchanged. No product code was changed for this review.

## Verdict

**The package architecture largely aligns with the design; runtime conformance is incomplete.** Keep the modular monolith, independent adapter distributions, domain-owned rules/verifiers, host-owned action ledger and provider-neutral UI. A rewrite or new service split is unnecessary. Two high-priority gaps affect task-success semantics and recovery independence. Six additional findings concern admission, feature compatibility, evidence provenance, readiness, observability and design synchronization.

Baseline: HLD §§4–9; MVP detailed design §§4–13; implementation plan §§0, 3, 9; accepted ADRs 0001–0014; topic designs for UI and integrations. ADR 0014 and the approved remediation plan specialize earlier transaction, uncertainty, budgets and scope wording. Live BigQuery, desktop and full knowledge governance remain explicitly deferred; their absence is not a regression against that approved scope.

## Findings and proposed fixes

### AR-01 — P1: verified intermediate output can become task success

Evidence: `packages/kernel/src/e_agent/kernel/coordinator.py:383` checks the last action's `VERIFIED` state before accepting final text; line 421 then marks the run `SUCCEEDED`. `_handle_answer` at line 727 verifies the selected answer capability but does not establish that it fulfills the user's requested task. The repeated-answer shortcut and recovery's latest-verified-action branch also need the same completion check.

Reproduction: request **“Create a draft purchase order for the shortage of widget-a.”** while the synthetic driver proposes a correct shortage answer. The host returns `SUCCEEDED`, with only `procurement.shortage.answer.v1` verified and **zero writes**. The shortage answer is accurate; the requested PO was never created. This is a success-classification defect, not an unauthorized write.

Design gap: MVP design §1 requires an approved draft PO and independent read-back; plan ERP-03 acceptance requires the matching draft order. Verifying one capability does not verify the entire task. The qualification script's task-specific oracle catches this in evaluations, but it is outside the production run-completion path.

Fix: introduce a bounded, host-admitted task acceptance specification, supplied by application/domain task definitions through public contracts/SDK. Keep ERP-specific decisions in the domain: a positive eligible shortage requires the verified draft PO; zero shortage permits a verified no-op; no eligible offer permits an explicitly accepted blocked/no-offer result. Intermediate recommendation/availability answers may continue planning. The model may propose intent but cannot authorize its own completion criteria. If free-text intent is ambiguous, clarify before admission rather than hard-code ERP keyword matching in the kernel.

Exit tests: shortage or recommendation alone cannot complete a positive draft-PO request; legitimate read tasks and no-op cases still complete; intermediate recommendation followed by PO remains supported; crash recovery and repeated answers use the identical acceptance check. Record the contract/boundary refinement in an ADR.

### AR-02 — P1: ledger recovery depends on restoring framework continuation

Evidence: coordinator `_load_cont` at line 262 restores the driver before returning the kernel continuation. Pydantic driver's `restore` at `packages/adapter-agent-pydantic/src/e_agent/adapters/pydantic_ai/driver.py:274` raises `ValueError` on incompatible schema/version. `_recover_run` at coordinator line 1453 catches only `KernelError`. Server lifespan at `apps/server/src/e_agent/server/api.py:318` awaits recovery before starting the worker.

Reproduction: persist an otherwise valid waiting-approval run with the current driver state schema and an incompatible Pydantic AI version. Calling `recover()` raises `ValueError: driver version changed; continuation cannot resume`; the run remains waiting. In server startup this exception aborts lifespan. Dispatching/committed recovery also currently requires a successfully loaded continuation.

Design gap: HLD §6, ADR 0003 and MVP design §10 require framework continuation to be replaceable and the business ledger sufficient to determine possible effects even when framework state cannot resume.

Fix: load trusted kernel context independently of optional driver restoration. Convert incompatible framework state into an explicit per-run continuation incompatibility; block inference/resumption until migration or a new approved run. Continue ledger recovery for possible effects: mark interrupted dispatch uncertain, preserve committed receipts and allow authorized reconciliation/read-back without framework history. Isolate malformed runs so one cannot stop all server recovery. Do not catch everything and guess success or no effect.

Exit tests: wrong framework version/schema and corrupt framework messages across waiting, dispatching and committed states; server can start, unaffected runs recover, ambiguous writes never replay, verified effects are handled without model resumption.

### AR-03 — P2: declared admission requirements and settings schemas are unused

Evidence: `packages/plugin-sdk/src/e_agent/sdk/manifest.py` declares `requires_capabilities` and `settings_schema`. Registry `admit`/`_check_admissible` (`packages/kernel/src/e_agent/kernel/registry.py:93`) checks version, artifact/manifest identity, SDK range and factory identity, then imports each plugin immediately. It does not validate the declared required capabilities or settings schema. Registration requires an existing contract for bindings, so lexicographic plugin order can also make otherwise valid provider/domain ordering fail.

Reproduction: a synthetic discovered ERP manifest declares a nonexistent required capability and a required setting that is absent. It is admitted and its factory runs. This fixture probe does not bypass or invalidate live artifact pinning; it demonstrates checks missing after identity admission.

Design gap: MVP design §6 startup steps 3–5 explicitly require compatibility, settings and required-binding checks before factories load.

Fix: preflight the full enabled metadata set, validate settings against declared schemas, resolve capability dependencies and configuration references, and establish deterministic dependency-aware registration. Reject missing/conflicting requirements before import. Validate contribution agreement and the complete executable registry before readiness. Keep factories side-effect-free and scoped.

Exit tests: absent requirement, invalid setting, invalid connection reference and incompatible metadata leave import markers untouched; valid domain/provider names in either lexical order work.

### AR-04 — P2: required capability features do not constrain routing

Evidence: descriptor `required_features` and binding `supported_features` exist in portable contracts, but registry `resolve` at line 215 only filters by contract and connection. Bootstrap `tool_specs` checks connection count, not feature eligibility.

Reproduction: a capability requires `conditional-read`; a sole binding supports no features. `resolve` still returns that binding.

Design gap: HLD §5 says resolution combines scope, compatibility and feature requirements; unsupported semantics must not be silently substituted (HLD §7).

Fix: enforce `required_features ⊆ supported_features` at activation and invocation. Apply the same eligible-binding rules when constructing model tool surfaces. Reject unsupported/ambiguous selection before provider calls. Include feature declarations in the admitted surface identity used for stale-approval checks.

Exit tests: incompatible sole binding rejected; feature-compatible candidate selected under explicit routing; two eligible candidates still fail on unresolved ambiguity. Current first-party empty feature sets do not prove this extension seam works.

### AR-05 — P2: exported version provenance belongs to export time

Evidence: `apps/server/src/e_agent/server/api.py:566` supplies the current runtime environment and `rt.versions` to `build_evidence`. `packages/kernel/src/e_agent/kernel/evidence.py` copies those values into the bundle. `RunRecord` and `run.created` do not persist the complete execution inventory. Bootstrap's runtime inventory includes the model name, not its frozen weight/context digest.

Reproduction: export the same stored run twice with different supplied model inventories; the bundle's `versions.model` changes. No run mutation is needed. A profile/model change across restart can therefore misattribute historical execution. Separate frozen qualification reports do retain model digests; that does not repair normal API evidence exports.

Design gap: HLD §§8–9, MVP design §11 and ADR 0010 require execution versions/provenance in evidence.

Fix: persist immutable run-admission metadata atomically with admission: environment, driver/distribution/plugin/artifact identities, relevant semantic bundles, policy and model/configuration fingerprint. Preserve execution-phase changes explicitly if permitted. Export original execution metadata separately from exporter metadata. Legacy missing provenance stays unknown rather than being filled with today's runtime.

Exit tests: model/profile/plugin changes after execution do not relabel old evidence; legacy runs report missing metadata; no secret settings or hidden reasoning enter the fingerprint/export.

### AR-06 — P2: readiness reports only successful initial construction

Evidence: `apps/server/src/e_agent/server/api.py:375` always returns HTTP 200 with `status=ready` once runtime exists. It does not inspect current store availability or worker health. Worker claim errors at line 198 are retried indefinitely. A dead ledger or stopped worker can coexist with a ready response.

Design gap: MVP design §12 distinguishes process liveness from required dependency/plugin readiness; §6 requires bounded health checks.

Fix: define readiness for the enabled local profile: bounded store probe and worker availability, plus cached/deadline-limited required-provider checks where appropriate. Return 503 with safe bounded reasons when unavailable; leave liveness separate. Do not perform unbounded inference or business reads on every probe.

Exit tests: dependency loss and worker termination make readiness false; recovery restores it; optional telemetry failure does not affect readiness.

### AR-07 — P2: accepted observability ADR has no product implementation

Evidence: accepted ADR 0008 requires server/kernel/adapter OpenTelemetry instrumentation, pinned GenAI conventions, trace linkage and default content exclusion. Repository searches found no product OTel configuration/instrumentation, EventObserver implementation or trace propagation. `RunEvent` has a generic `correlation_id`, not the promised trace/span linkage. Framework transitive dependencies alone do not implement the ADR.

Fix: implement the bounded accepted observability slice, with content capture off, bounded labels, explicit semconv configuration and nonfatal exporter failure. If this is deliberately deferred, record a superseding scope decision and update affected design/plan claims; do not quietly treat an accepted ADR as optional work already done.

Exit tests: in-memory exported spans contain no seeded prompt/tool/secret values; traced durable events link to execution traces; exporter outage does not block mandatory evidence or writes whose ledger is healthy.

### AR-08 — P3: authoritative documents contradict current status/scope

Evidence: HLD line 4 says research/design only; MVP detailed design line 4 says not implemented; plan §3 line 97 says only I01/I02 are done and the rest are not started. HLD/plan still describe live BigQuery as an MVP gate while accepted ADR 0014 and the approved remediation defer it. The plan still prohibits starting I10/I11 before live I07/I09, though all task source now exists. The detailed design's PostgreSQL text still describes transaction-scoped dispatch locking alongside the clarified short-transaction model.

Fix: reconcile implementation availability, demonstrated gate status and approved scope across these documents. Retain historical decision dates; distinguish implemented source from live qualification. Rewrite the active dependency/gate table and cross-reference ADR 0014 at contradictory sections. Do not mark blocked live milestones passed merely because source exists.

Exit check: a new developer can read HLD → detailed design → plan → README and obtain one consistent active scope and gate status.

## Alignment matrix

| Boundary | Assessment | Evidence/limits |
|---|---|---|
| Modular monolith, independent distributions, namespace | Aligned | Seven import contracts pass; prior remediation records ten clean wheel closures. Clean wheel builds were not repeated in this review. |
| Contracts → SDK → kernel; domain/provider separation | Aligned | Kernel does not import ERP or adapters; Odoo uses public domain DTOs; concrete wiring is in bootstrap. |
| Ontology/rule ownership and independent acceptance | Largely aligned | Domain resources/dataset builders/verifiers; SHACL engine adapter. Whole-task completion remains AR-01. Full ontology effectiveness and multidomain product qualification are not claimed. |
| Authorization, exact approval, independent read-back | Largely aligned | Host gateway, current-fact/authority checks, approved baseline and provider correlation; focused verification regressions pass. Owner Odoo races remain untested. |
| Durability and external uncertainty | Largely aligned | Short transactions, durable work fencing, mandatory dispatch evidence and conservative reconciliation; framework-independent recovery remains AR-02. |
| Metadata-only discovery and trusted artifact identity | Partial | Existing pins/tamper tests pass; semantic admission and feature routing remain AR-03/04. |
| Odoo addon boundary | Aligned in source | `adapter-odoo` is the client; addon owns atomic bounded ERP mutation/operation identity. No cross-database transaction. Owner install, ORM ACLs and simultaneous-call behavior remain unqualified. |
| UI layering, replaceability and provider neutrality | Aligned in dependency structure | Shared client/core, React bindings/components/layouts, Shadow-DOM overlay and vanilla reference host; fresh boundary and neutrality checks pass. |
| UI customization detail | Partial, lower priority | Layout parser supports preset/visibility/side, but not the designed slot `order`; sidebar is a stack rather than specified tabs, overlay approval/evidence are inline rather than modal/drawer. Only panel styling part is implemented, already disclosed in UI design §9. Record these as bounded MVP presentation differences or finish them before claiming every customization tier. |
| Telemetry, dependency readiness and execution provenance | Partial | AR-05/06/07. |
| Eight ERP tasks and release gate | Source present; live gate open | Prior fixture/model qualification is distinct from installed owner Odoo and human-approved integrated trials. |
| BigQuery/knowledge/admin/OAuth expansion | Deferred | Approved scope/Phase 2; no unused future packages are needed. Synchronize older scope text under AR-08. |

## Fix order and review evidence

1. AR-01/02: preserve domain-defined task acceptance and ledger independence; document any new portable contract in an ADR.
2. AR-03/04/05: complete admission/routing and persist execution provenance before integrated qualification.
3. AR-06/07: dependency readiness and the accepted observability slice.
4. AR-08: synchronize designs and active milestones alongside the fixes; explicitly track remaining UI presentation differences.
5. Run clean artifact/contract checks, then exact approved sandbox integration and human-approved model/API/UI release trials. All eight task gates remain enabled.

Fresh checks during this review:

- `uv run lint-imports`: **7 kept, 0 broken**.
- `uv run pytest -q packages/kernel/tests/test_registry.py packages/kernel/tests/test_host_context.py apps/server/tests/test_business_verification.py apps/server/tests/test_recorded_model_replays.py`: **71 passed**.
- `pnpm --dir ui lint:boundaries`: no violations, 51 modules/85 dependencies.
- `pnpm --dir ui lint:neutral`: passed.
- `uv run python evidence/architecture/20261007-alignment/probes.py`: five synthetic counterexamples recorded in `probes.json`; wrong-task completion, export provenance, incompatible continuation, missing plugin requirements/settings and unsupported feature routing. The initial probe invocation had a helper attribute typo, corrected before recording the results; no product failure is inferred from that typo.

The probes use the memory store, fixture ERP and synthetic manifest/driver metadata. No model inference, external business reads, Odoo installation or owner-container changes were performed. They show missing host invariants, not live service behavior. Historical 317-test/47-browser/model-series results remain in the separate remediation report; they were not rerun or relabeled here.
