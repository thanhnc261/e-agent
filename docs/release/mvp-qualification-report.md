# MVP release qualification report (I14)

**Date:** 2026-10-06. **Scope:** what the repository demonstrably does today, which environment each claim was tested in, and what remains before the MVP can be called complete on the owner's machine. This is not a production-readiness or certification claim.

## 1. Verdict

| Area | Status |
|---|---|
| Host safety path (kernel, rules, approval, ledger, recovery, verification) | **Qualified** on fixtures and PostgreSQL 16 |
| Eight Odoo tasks ERP-01..08 | **Qualified with the scripted driver against a live Odoo 19 sandbox** (built from source in the dev container) |
| Streaming API and layered UI (default app, overlay, reference UI) | **Qualified** against the fixture server (41 Playwright conformance tests) |
| Local model driver (Pydantic AI + Ollama) | Driver implemented and tested with deterministic models; **live model qualification pending** on the owner's machine (Ollama registry blocked in the container) |
| Owner's `odoo19-learning` stack | **Pending**: install the bridge per the [I06 runbook](../runbooks/i06-odoo-bridge.md) |
| BigQuery BQ-01/02 (I12/I13) | **Blocked** on decision D6 (project, region, data permission) |

The MVP is feature-complete for the Odoo scope and UI. Three owner-side gates remain (§6) before the release criteria in the [implementation plan](../implementation-plan.md) are fully met.

## 2. Gates run for this report

All commands are in the README and run in CI unless marked *local*.

| Gate | Command | Result |
|---|---|---|
| Lint and format | `uv run ruff check . && uv run ruff format --check .` | pass |
| Types (strict) | `uv run mypy` | pass (90 source files) |
| Architecture | `uv run lint-imports` | 7/7 contracts kept (layers; kernel ⇸ domain/server; domain ⇸ kernel/server; adapters isolated; bounded contexts procurement/inventory/sales/crm/receivables independent; no framework/provider SDK in core) |
| Unit, integration, API | `uv run pytest -q` | 197 passed (with live Odoo variables set; without them the 19 live tests skip) |
| Kernel + store conformance on PostgreSQL | `E_AGENT_TEST_STORE=postgres uv run pytest -q packages/kernel tests/conformance` | 66 passed |
| Live Odoo 19 (*local* + nightly `odoo-live`) | `uv run pytest -q tests/integration/test_odoo_live*.py` | 19 passed |
| Independent artifacts | `uv run python scripts/check_wheels.py` | every wheel installs and imports from its own dependency closure; installed demo plus ERP-04..08 demos succeed outside the repository |
| Release task matrix | `uv run python scripts/release_report.py` | 21/21 cases ([report](../../evals/reports/fixture-release.json)) |
| OpenAPI and generated TS | `scripts/export_openapi.py --check`, `pnpm gen:check` | current |
| UI checks | `cd ui && pnpm check` | typecheck, 38 Vitest tests, dependency-cruiser layer rules, provider-neutrality gate, builds |
| UI conformance | `cd ui && pnpm conformance` | 41 passed (default, overlay on a hostile host page, non-React reference UI) |

## 3. Task coverage

| Task | Capability | Fixture (scripted) | Live Odoo 19 (scripted) | Live model |
|---|---|---|---|---|
| ERP-01 shortage | `procurement.shortage.answer.v1` (verified answer) | pass; wrong answer fails verification then corrected | pass | pending |
| ERP-02 offer recommendation | `procurement.offer.recommend.v1` | pass | pass | pending |
| ERP-03 draft PO | `procurement.purchase-order.create-draft.v1` | pass; PR-003 block + repair; over budget; reject; lost response → reconcile | pass incl. 6-way race → 1 PO, lost response | pending |
| ERP-04 amend draft RFQ | `procurement.draft-rfq.amend.v1` | pass; stale revision (AM-002) block + repair; confirmed RFQ (AM-001) | pass; bridge re-checks draft + revision (`E_AGENT_STALE`) | pending |
| ERP-05 draft quotation | `sales.quotation.create-draft.v1` | pass; off-list price (SQ-003) + repair; unsaleable (SQ-002) | pass; draft and unsent; archived customer rejected | pending |
| ERP-06 late orders | `sales.late-orders.answer.v1` | pass; wrong answer fails verification | pass (late included; future and delivered excluded) | pending |
| ERP-07 CRM lead | `crm.lead.create.v1` | pass; owner outside team (CL-002) + repair; lost response | pass; repeated command returns the same lead | pending |
| ERP-08 overdue invoices | `receivables.overdue-invoices.answer.v1` | pass; wrong totals fail verification | pass; open invoices unchanged (read-only) | pending |

"Scripted" means the deterministic driver in `e_agent.erp.testing`; it exercises everything except the model's choices. Read-only tasks never request approval and never call a provider write.

## 4. Threat model coverage

| Threat | Mitigation in code | Test evidence |
|---|---|---|
| T1 goal hijack | Fixed tool set per run; rules independent of model text | Rule matrices; model-level injection evals pending live model |
| T2 tool misuse | Narrow bridge commands, gateway scope, SHACL rules, approval | `test_procurement_rules.py`, `test_erp_task_rules.py`, live bridge rejections |
| T3 privilege | Dedicated integration user (purchase/stock/sales/read-only accounting); identity from server session only | live `test_integration_user_cannot_run_sandbox_tools`; API session tests |
| T4 supply chain | Locked deps; manifest digest admission | `test_manifest_digest_must_match_inventory`; wheel gate |
| T5 code execution | No code/SQL tools exist | n/a until BigQuery templates (I12) |
| T6 context poisoning | Per-run continuation only; no cross-run memory | by construction; no dedicated test |
| T7 inter-agent | Single agent | n/a |
| T8 cascading failures | `UNKNOWN` + read-only reconciliation, writer lock, no auto-retry | lost-response tests (fixture and live), 6-way race |
| T9 approval fatigue | Server-built `ApprovalPresentation`, changed-field marking, findings | UI conformance 1, 2, 5 |
| T10 rogue loops | Kernel budgets, cancel | `test_repair_budget_exhaustion_fails_run`, `test_cancel_before_dispatch`, `test_write_budget_limits_admitted_writes` |
| T11 exfiltration via rendering | Text-only rendering, no remote images, full URLs | UI conformance 4 (no network request) |
| T12 reasoning leakage | Thinking parts stripped before persistence | `test_no_hidden_reasoning_reaches_the_ledger` |
| T13 cross-border transfer | BigQuery not connected | blocked on D6 |
| T14 wrong environment | Sandbox marker at startup | live `test_wrong_sandbox_marker_refuses_to_start` |
| T15 CSRF / cross-origin | Loopback session, HttpOnly SameSite=Strict cookie, CSRF header | `test_requests_without_session_or_csrf_are_rejected` |
| T16 ledger co-located with ERP DB | Startup refuses a ledger DSN naming a provider database | `test_ledger_must_not_share_the_provider_database` |
| T17 tool-schema drift | Capability-surface digest pinned at run start; approval after drift is blocked | `test_capability_surface_change_blocks_resume` |
| T18 credential exposure | Envelope-encrypted secret store; redacted `Secret`; keys never in events | credential and secret-store tests; live test asserts the key is absent from events |
| T19 confused deputy | Connection scope, delegated-connection ownership, credential subject in the digest | `test_credentials.py`, `test_lifecycle.py` (rotated subject requires re-approval) |

## 5. Known limitations

- Live model behaviour (tool choice, repair, refusal) is unmeasured; ADR 0010 pass^k trials must run on the owner's machine.
- The UI was tested against the fixture server. It needs no change for live Odoo, but no live UI session has been recorded.
- The scripted driver selects the task from the profile (`driver.task_kind`); free-text routing between tasks is the model's job and is untested until live model runs.
- ERP-04 supports single-line draft RFQs only; ERP-06/08 reads are capped (500 orders, 1000 invoices) and mark the evidence incomplete beyond that.
- Single process, loopback-only local session. Multi-worker leases, production authentication and the Phase 2 admin pages are out of MVP scope.
- `AskClarification` is persisted but there is no API endpoint to answer it yet; driver text streaming (token deltas) is not implemented. The SSE stream carries run events.

## 6. Owner gates to close the MVP

1. **Environment (I00):** run `scripts/env_check.py` and the [I00 runbook](../runbooks/i00-environment-qualification.md).
2. **Bridge on `odoo19-learning` (I06):** install `e_agent_bridge` 19.0.0.2.0, create the integration user with the groups listed in the runbook, set the sandbox marker, then run `scripts/odoo_sandbox.py seed-tasks` and the live tests against it.
3. **Model qualification (I04/ADR 0010):** `uv run python scripts/qualify_model.py --model <candidate> --trials 10`, keep every trial in `evals/reports/`, and record the selected model in the profile.
4. **Live demo:** follow the [demo runbook](../runbooks/demo.md) with the qualified model and the UI.
5. **D6:** decide BigQuery scope before I12/I13 start.
