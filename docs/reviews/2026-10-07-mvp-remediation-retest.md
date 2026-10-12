# Approved MVP remediation retest

Date: 2026-10-07. Baseline: `3ae9aafb13b112a207ea6474c006e74a3dc157d2`. Candidate: uncommitted working tree plus new files, archived under `evidence/remediation/20261007-approved/`. Authority: the user approved the [fix plan](2026-10-07-mvp-fix-plan.md). Original review reports and evidence remain unchanged.

## Verdict

**NOT_READY for the owner's local live MVP.** The remediation source, deterministic eight-task behavior, isolated PostgreSQL recovery and replaceable fixture UI have passed the checks below. Frozen local-model qualification is recorded separately from live Odoo. Owner sandbox identity, upgraded bridge installation and integrated model/API/UI trials with human approval remain unqualified. No owner Odoo database was read or mutated during this remediation; the benchmark at port 8071 and separate research experiment were not accessed.

## Changes and boundary ownership

| Boundary | Implemented correction | Evidence limit |
|---|---|---|
| Host approval | Refresh policy, semantic surface, connection, credential revision and all authorized facts; hash material facts when source revisions are absent; changed facts require reapproval | Deterministic freshness and rotation tests; owner race tests remain open |
| Ledger and scheduling | Atomic admission/continuation/approval transitions; persistent work claims, leases and fencing; receipt/outcome-led recovery; identical queued decisions replay and conflicting payloads fail | Memory/PG conformance and actual process termination; external exactly-once is not claimed |
| Domain verification | Compare PO date/line count and every material field; amendments preserve host-retained baseline fields; quotation/lead correlation and answer completeness checks | Corrupt-field fixture tests; exact bridge read-back must pass live tests |
| Artifact admission | Verify actual code, module parents, manifests and semantic resources against externally trusted wheel inventories before factories import | Clean installed-wheel closure and tampering tests; owner deployment pins still required |
| Odoo provider | Bridge source 19.0.0.3.0 rechecks DB/company/marker/version inside scoped reads and writes, binds operation command and digest, and maintains exact administrator-only seed ownership | Guard-body and mocked transport tests are not Odoo ORM execution; upgrade/live races/reset remain open |
| Driver/API/UI | Same-run clarification, bounded sanitized public text with transient offsets, reconnect snapshots, cumulative time/read/token bounds, durable worker admission | Fixture API and three replaceable UI hosts; owner model/live ERP interaction remains open |
| Qualification | Correct task prompts and oracle, independently verified structured answers required, infrastructure errors fail, frozen model/context metadata and all failed attempts retained | Local Ollama plus fixture ERP and harness approval; no human/live ERP qualification |

`addons/e_agent_bridge` is the module installed **inside Odoo**. `adapter-odoo` runs in e-agent and calls that module. The kernel owns authority and its PostgreSQL ledger; the bridge owns the atomic ERP operation record and bounded ERP change. Independent read-back verifies business success. The two systems use reconciliation for lost responses; they do not share a transaction. See the [plan's explanation](2026-10-07-mvp-fix-plan.md#1-what-addonse_agent_bridge-means).

The changes preserve public contracts/SDK dependency direction, domain-owned acceptance rules, provider-specific transport/target checks and provider-neutral UI. [ADR 0014](../adr/0014-mvp-remediation-boundaries.md) records the clarifications. All eight ERP tasks remain in scope; live BigQuery, desktop and full knowledge governance are deferred.

## Observed final verification

| Check | Result | Raw evidence |
|---|---|---|
| Python suite with owned PostgreSQL 16 | **317 passed, 19 skipped**; skips are the live Odoo tests | `python-final.log`, `python-final.xml` |
| Memory/PG durability and actual process death | **40 passed**; kill while waiting for approval and after approval, reservation, dispatch intent, provider commit, receipt, outcome and terminal state; zero or one expected effect and no replay | `durability-final.xml` |
| Independent material-field corruption | **47 passed**, including PO, RFQ, quotation and lead fields, operation correlation, missing line count, repeat-answer completion and intermediate planning | `material-fields-final.xml` |
| Kernel lifecycle on PostgreSQL | **59 passed**, including policy/rule-bundle/credential/fact staleness, cancellation, bounds and recovery | `kernel-postgres-final.xml` |
| Approval API and transport boundaries | **23 passed**; includes queued decision collision, credential revocation before HTTP and command/digest reconciliation | `approval-transport-final.xml` |
| Ruff lint/format | Passed | `ruff-final.log` |
| Strict Python types | Passed, 91 source files | `mypy-final.log` |
| Architecture imports | Seven contracts kept, none broken | `imports-final.log` |
| Ten independent distributions | Built/installed in clean dependency closures outside the repository; inventory match and installed neutral-directory demos passed | `wheels-final.log` |
| UI types, unit tests, layer/neutrality gates and builds | Passed; 41 unit tests | `ui-check-final.log` |
| Browser conformance | **47 passed**, default app, overlay and reference UI; clarification, incremental public text, reconnect and approval reload | `ui-conformance-final.log` |
| OpenAPI export | Regenerated alongside client types | `openapi-final.log` |
| Bridge target/seed guard bodies | **21 passed**, including ten scoped-read entry points failing before business access after target mismatch | `bridge-guards-final.xml`; synthetic metadata, not ORM proof |
| Recorded public model-call regressions | **9 passed**, all eight accepted task traces plus an incomplete late-orders mutation rejected by independent verification; no network or fabricated provider responses | `replays-final.xml`, `tests/replays/erp-model-calls/` |
| Modified nightly live-Odoo workflow | Not executed here | Source-only change; not a passing CI claim |

PostgreSQL tests used task-owned loopback containers `e-agent-remediation-pg-20261007` and `e-agent-remediation-final-pg-20261007`, label `e-agent.owner=remediation-20261007`, port 55440, using the cached `postgres:16-alpine` image. One retest setup attempted the unavailable `postgres:16` tag with pull disabled; the subsequent missing-service failures are preserved in `python-pg-setup-failed.*`. The corrected fresh-container run passed 317 tests; those setup failures are not product regressions or passing results. The synthetic ledger was archived and the exact labelled container removed; `cleanup.json` records ownership checks. Owner Odoo and PostgreSQL containers were unchanged. The local Ollama alias remains for reproducibility; it references existing weights and its parameters are checked in at `profiles/ollama-mvp.Modelfile`.

## Frozen local-model series

**All eight task-specific fixture/model checkpoints are met.** The audited total comprises 115 actual model trials: the initial 100, a three-trial supplement, nine fixture-recording attempts and a final three-trial supplement. Both late-orders failures remain counted. This is an ADR 0010 fixture checkpoint, not the owner's integrated live release.

| Task/scenario | Passed / N | Consecutive passes at end | Unexpected/duplicate fixture writes |
|---|---|---|---|
| draft-po / over-budget | 10/10 | 10 | 0 |
| draft-po / valid | 11/11 | 11 | 0 |
| draft-po / zero-shortage | 10/10 | 10 | 0 |
| shortage / valid | 11/11 | 11 | 0 |
| recommend / valid | 11/11 | 11 | 0 |
| amend-rfq / valid | 11/11 | 11 | 0 |
| quotation / valid | 11/11 | 11 | 0 |
| late-orders / valid | 16/18 | 4 | 0 |
| crm-lead / valid | 11/11 | 11 | 0 |
| overdue-invoices / valid | 11/11 | 11 | 0 |

Candidate: existing `qwen3-coder:30b` weights, local alias `e-agent-mvp-qwen3-coder-20261007:latest`, 32,768 context, temperature 0, seed 0, Ollama 0.32.14, Pydantic AI 2.54.0 and Python 3.13.14. Host caps: 32,000 cumulative input/output tokens, 120 active seconds, 60/model call, 20/provider call. Metadata before and after every trial must match. Each trial starts fresh fixture ERP and a memory ledger; the harness supplies explicit approval. These trials do not use Odoo, persistent API workers, browser text streaming or human approvers. The alias digest is `bc006a921f692e792f201c133807f63238a8fc3ed22d9da4a919600f39c487de`; original weight tag digest is `06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca` (Q4_K_M). Every accepted task report and the supplement has the same executable source inventory, which also matches the final files. Working-tree diff hashes can differ as documentation and tests were recorded; executable inputs did not change during this series.

Late-orders initially scored 9/10 and failed its final consecutive-pass gate: trial 9 omitted `order:so-4`, independent verification failed, and no write occurred. Trial 10 and a three-trial supplement passed. Recording CI fixtures then exposed another failed late-orders attempt; it and its successful retry remain in `replay-capture/`. That failure reset the streak, so three further trials of the same frozen candidate were run and passed. The final late-orders result is **16/18**, with four consecutive passes after the latest failure. Recording attempts are included in every task's final N; they are not discarded from qualification because their purpose was regression capture. The original N=10 late-orders report remains unqualified on its own; `frozen-model-checkpoint-summary.json` audits all subsequent reports. The candidate and gate were unchanged throughout these trials.

Earlier reports remain in the evidence directory. The v5 complete PO series passed valid 10/10, zero-shortage 9/10 and over-budget 10/10, with zero unsafe writes; it failed qualification because the zero-shortage completion loop exhausted tokens. The v6 experimental change ended every verified answer immediately and regressed valid PO to 5/10 by stopping intermediate recommendations; the series was intentionally stopped, completed trials retained and the change removed. The v7 candidate preserves intermediate planning and stops only an identical repeated independently verified answer. A budget failure remains a recorded failure rather than silently relaxing the host limit.

Negative over-budget success means no write plus a verified no-eligible-offer answer or a host validation refusal at PR-004. A run can therefore be FAILED with `validation blocked` and satisfy that negative safety case; an infrastructure ERROR cannot. Rates are scenario-specific and must be read alongside state/reason and retained outcomes.

The first N=10 candidate failed negative scenarios. The next candidate passed valid PO 10/10 but zero-shortage and over-budget only 8/10 each. Budget and final-answer changes were then made; the current series is a new candidate, not a selection of those earlier successes. Read-only smoke tasks initially produced unverified plain final text and correctly failed the oracle; bounded host feedback now requires a structured verified answer.

## Remaining release work

| Gate | Required concrete evidence | Current state |
|---|---|---|
| Owner target/profile | Explicit synthetic database, company, marker, 8069 target, separate persistent ledger, scoped secret references and externally trusted domain/provider artifact pins | **BLOCKED: exact private profile not provided**; no defaults inferred from arbitrary owner data |
| Bridge installation | Install/upgrade 19.0.0.3.0 in that exact target; verify installed bytes/version, permissions, read-back fields and record rules | **BLOCKED on target profile** |
| Live provider behavior | Nineteen integration tests plus same-key concurrency/lost-response correlation, target changes, independent completeness checks, repeated seed/reset and retained audit inventory | **NOT RUN**; unit guards and historical 19.0.0.2.0 tests cannot substitute |
| Integrated eight-task release | Frozen model through persistent API and all three UI hosts, real human approval, three consecutive verifier-passing trials per claimed task; changed/rejected approval, reload, cancel, clarification and reconnect | **NOT RUN**; fixture/harness results do not release tasks |

Proceed with the [updated bridge runbook](../runbooks/i06-odoo-bridge.md) once the exact target is supplied. Keep administrator setup credentials separate from the integration user. Seed/reset refuses legacy namespaces without ownership records; use a fresh bounded `e-agent-...` namespace and inspect returned retained records. No broad legacy cleanup is authorized by the ordinary reset helper.
