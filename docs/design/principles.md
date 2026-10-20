# e-agent: principles and their checks

**Date:** 2026-10-14. **Status:** consolidated from existing sources; it adds no new principle. Checks were verified against `main` at `8bc7b1f` with the 2026-10-14 working tree. The checks of PR-01, PR-03, PR-08 and PR-10 were re-verified at the close of Phase 1d (2026-10-16, branch `refactor/phase1d-plugin-boundary`).

This file is the spine of the design ([adoption review](../reviews/2026-10-14-x-agent-adoption-review.md) XA-00). Each row gives a binding principle, what it means in practice, where it was decided, the engineering rule that applies it, the **check that enforces it** and its status.

How it relates to the other documents:
- **This file** states each principle once, with its check.
- **The ENG rules** (`.agents/skills/eng-foundations/references/rules.md`) say how engineers apply them.
- **AGENTS.md** summarises and links here.
- **The HLD, MVP design and target architecture** hold the mechanisms, and cite rows here instead of restating the principles.

A principle with no check is a backlog item, not an assumption. The backlog is listed at the end.

Status tags follow the target architecture: **[I]** implemented, **[Pa]** partial, **[P]** proposed, **[C]** conditional. "**none**" in the check column means that no machine check exists; only review enforces it.

## Architecture

| ID | Principle | In practice | Decided in | ENG | Check | Status |
|---|---|---|---|---|---|---|
| PR-01 | Dependencies point one way | contracts ← sdk ← kernel and domains ← adapters ← server; the kernel never imports domains, adapters or server | AGENTS.md; HLD §4 | ENG-ARCH-1 | 12 import-linter contracts (`pyproject.toml:90-189`), `uv run lint-imports` in the `full` gate | [I] |
| PR-02 | Contracts are portable records | No vendor, framework or ORM type crosses a contract; domain fields live in domain APIs | AGENTS.md | ENG-ARCH-2 | Import contract "Core packages do not import agent frameworks or provider SDKs" forbids `pydantic_ai`, `httpx`, `psycopg`, `fastapi` in contracts, sdk, kernel and erp; vendor-shaped fields are review only | [Pa] |
| PR-03 | Bootstrap composes; handlers, CLI and prompts hold no domain logic | Bootstrap picks implementations; HTTP and CLI delegate | AGENTS.md; HLD §4 | ENG-ARCH-3 | `test_server_has_no_domain_literals` (`tests/unit/server/test_generic_composition.py:146`) finds no ERP literal in `src/e_agent/server/`; that handlers and prompts hold no domain logic beyond literals stays a review item | [Pa] |
| PR-04 | No speculative structure | No unused abstraction or empty future package; a seam exists for a concrete use or a trust boundary | AGENTS.md | ENG-ARCH-4 | **none** | [I] by review |
| PR-05 | One namespace tree, independently releasable wheels | `src/e_agent/<part>/`, one build config per distribution, no namespace `__init__.py` | AGENTS.md; HLD §4 | ENG-ARCH-5 | `tests/conformance/test_repo_layout.py`; `scripts/check_wheels.py` | [I] |
| PR-06 | Never loosen a boundary to make a change fit | No import-contract exemption or ignore added for convenience | Adoption review (X-agent gaps AP-03, AP-06) | none | **none** | [I] by review |

## Plugins and integration

| ID | Principle | In practice | Decided in | ENG | Check | Status |
|---|---|---|---|---|---|---|
| PR-07 | Discover metadata before import; activate only admitted artifacts | Disabled plugins are never imported; manifests are digest-pinned | AGENTS.md; MVP §6 | none | `test_disabled_plugin_is_never_imported` (`tests/unit/kernel/test_registry.py:140`); `test_manifest_digest_must_match_inventory` (`:171`) | [I] |
| PR-08 | Plugins are guests | Plugins never import the store, the secret store, the server or kernel internals; credentials arrive only through scoped services | AGENTS.md; adoption review XA-02 | ENG-ARCH-1 | Import contract "Plugins are guests" (`pyproject.toml:111-115`): the ERP plugin packages never import the kernel, the server, the store, the secret store, the driver or the validator; `test_every_plugin_package_is_a_guest` (`tests/conformance/test_plugin_guests.py:45`) fails when an installed plugin package is not a source of that contract; "Core never imports plugins" (`pyproject.toml:105-109`) forbids `e_agent.plugins.**` from contracts, SDK, kernel and server; plugin distributions depend only on contracts, the SDK and the domain packs they bind (`test_plugin_dependencies_are_the_common_base`, `tests/conformance/test_plugin_dependencies.py`). Credentials reaching plugins only through scoped services is PR-25 | [I] |
| PR-09 | Domain, capability, binding and connection stay separate; ambiguity is an error | Multiple bindings allowed; duplicates and ambiguous routing refused | AGENTS.md; HLD §5; ADR 0002 | none | `test_duplicate_binding_id_rejected` (`tests/unit/kernel/test_registry.py:48`); `test_duplicate_bindings_on_one_connection_are_ambiguous_not_available` (`tests/unit/kernel/test_discovery.py:192`) | [I] |
| PR-10 | A declared capability requirement is enforced, or the capability is absent with a reason | `required_features` checked at admission | Adoption review XA-03 | none | The registry refuses a binding whose `supported_features` lack its capability's `required_features` (`kernel/registry.py:230-236`): `test_binding_missing_required_feature_refused`, `test_binding_missing_required_feature_refused_without_a_connection` and `test_binding_with_required_features_admitted` (`tests/unit/kernel/test_registry.py:292-312`). Probing a live instance for its features is Phase 5 | [I] |
| PR-11 | UI packages carry no provider or third-party identifiers | Names, icons and forms come from manifests through the server API | AGENTS.md; ADR 0011 | none | **none** | [I] by review |
| PR-12 | Model output never selects credentials or connections | Host resolution picks binding and connection | AGENTS.md; HLD §5 | ENG-TRUST-1 | **none** (Phase 2 adds `test_plan_with_model_chosen_connection_is_rejected`) | [Pa] |

## Trust anchor

| ID | Principle | In practice | Decided in | ENG | Check | Status |
|---|---|---|---|---|---|---|
| PR-13 | Model output is a proposal | It cannot approve, change policy or budgets, install plugins, publish ontology or mark its own task verified | AGENTS.md; roadmap rule 4 | ENG-TRUST-1 | `test_verifier_rejects_inexact_readback` (`tests/unit/plugins/erp/domain/test_procurement.py:266`) for answers; Phase 2 adds `test_model_cannot_mark_plan_verified` | [Pa] |
| PR-14 | The kernel owns the state machines; every tool call goes through the gateway | Transition tables in contracts, enforced by the kernel | Roadmap rule 4; ADR 0018 | ENG-TRUST-2 | `test_run_transition_table_covers_every_state_and_terminals_are_final` (`tests/unit/contracts/test_records.py:115`); `test_terminal_run_rejects_further_transitions` (`tests/unit/kernel/test_lifecycle.py:590`); import contracts "Core never imports plugins" and "Layered dependency direction (HLD §4)" | [I] |
| PR-15 | Approval binds the exact action, scope and versions | Stale approval rejected; no self-approval unless the profile allows it | ADRs 0006, 0014, 0019 | ENG-TRUST-3 | Digest golden vectors (`src/e_agent/contracts/golden/digest_vectors.json`, `tests/unit/contracts/test_digest.py`, `ui/packages/ui-core/test/digest.test.ts`); `test_requester_cannot_approve` (`tests/unit/kernel/test_lifecycle.py:66`); `test_ready_reports_whether_self_approval_is_allowed` (`tests/unit/server/test_api.py:461`) | [I] |
| PR-16 | Nothing modifies an action after its approval digest | Changes only before the digest, shown to the approver; text replies may be redacted | Owner D-4; ADR 0024 | ENG-TRUST-3 | The bridge rejects a payload-digest mismatch (`addons/e_agent_bridge/models/bridge.py:234-237`); the guardrail rule has **none** (no guardrails yet) | [Pa] |
| PR-17 | Evidence before writes; local state atomic; no transaction across a model or ERP call | Admission and dispatch evidence persisted first | ADR 0003; MVP §9 | ENG-TRUST-4 | `tests/conformance/test_run_store.py` on both stores | [I] |
| PR-18 | An unknown outcome stays unknown | No blind replay; reconciliation; no exactly-once claim | ADR 0014; MVP §9 | ENG-TRUST-5 | `test_lost_response_reconciles_without_a_second_write` (`tests/unit/server/test_erp_tasks.py:82`); `test_lost_response_is_unknown_until_reconciled` (`tests/unit/server/test_walking_skeleton.py:66`) | [I] |
| PR-19 | Outcomes are verified by independent read-back | Committed effect is distinct from verified business success | MVP §7–§8 | ENG-TRUST-5 | `test_verifier_rejects_inexact_readback` (`tests/unit/plugins/erp/domain/test_procurement.py:266`) | [I] |
| PR-20 | Every capability declares its effect | `risk`, `reversibility` on contracts; `idempotency` on bindings; live profiles refuse defaults | Adoption review XA-01; ADR 0029 | none | **none** | [P] |
| PR-21 | Results are never fabricated | An error is never an empty result; a bounded result is marked partial | Adoption review AP-15; ADR 0030 | none | Completeness `COMPLETE/PARTIAL/UNKNOWN` (`contracts/evidence.py:11-14`); in the model's context (Phase 3 Task 3d.2, ADR 0032): a bounded observation is `partial` and `truncated` with each cut logged, and a dropped or cleared one keeps its `EvidenceRef` as a marked stub (`test_bounded_observation_is_partial_with_truncated_marker`, `test_layer_over_budget_drops_oldest_and_logs_it`, `test_cleared_result_keeps_evidence_ref`, `tests/unit/kernel/test_context_assembler.py`); a read error is an error entry, never an empty result (`test_error_is_never_rendered_as_empty_result`, `tests/unit/kernel/test_context_assembler.py`); `RenderedObservation` refuses `partial` without a reason (`test_rendered_observation_partial_requires_marker`, `tests/unit/contracts/test_context_pack.py`). Per-capability markers (Phase 5) have **none** | [Pa] |
| PR-40 | Auto-approval is a benchmark-only setting | Only a profile marked benchmark-only (`operator.benchmark_auto_approve`) may auto-approve, only `read` and `write_low` steps with explicit (not defaulted) declarations, and never with `environment: live` | Owner D-3; ADR 0024 | ENG-TRUST-3 | **none** (no auto-approve setting exists yet) | [P] |

## Toggles

| ID | Principle | In practice | Decided in | ENG | Check | Status |
|---|---|---|---|---|---|---|
| PR-22 | Every new runtime feature has an `off/shadow/on` toggle with fallback only before a reservation, reported in readiness and evidence | `Profile.features`; `feature.fallback` | Roadmap rule 3; ADR 0027 | ENG-TOGGLE-1, -2, -3 | **none** (no `Profile.features` yet; Phase 2) | [P] |
| PR-23 | `shadow` compares and acts on nothing; a toggle is not cover for a stub | Shadow records a comparison with the live path | Adoption review XA-24; ADR 0027 | ENG-TOGGLE-1 | **none** | [P] |

## Data and security

| ID | Principle | In practice | Decided in | ENG | Check | Status |
|---|---|---|---|---|---|---|
| PR-24 | Tenant scope on every row and query; a foreign record looks absent | Composite tenant keys; host-derived scope; FORBIDDEN maps to 404 | AGENTS.md; MVP §9 | none | Composite keys (`src/e_agent/adapters/postgres/migrations/0001_initial.sql`); `test_other_tenant_cannot_use_connection` (`tests/unit/kernel/test_lifecycle.py:256`); `test_requests_without_session_or_csrf_are_rejected` (`tests/unit/server/test_api.py:36`); RLS is Phase 7 | [Pa] |
| PR-25 | Credentials never appear in logs, prompts, traces, evidence or the repository; plugins never hold a raw credential | Secret refs only; redacted `repr`; no `materialize()` | AGENTS.md; owner D-1 | ENG-BOUND-3, ENG-EVID-3 | `test_secret_repr_is_redacted` (`tests/unit/adapters/secretstore_local/test_local_store.py:40`); the plugin HTTP helper never logs or chains a header or body (`test_http_never_echoes_credentials`, `tests/unit/sdk/test_http.py`); harness redaction (`tools/harness/src/e_agent_harness/gate.py`, `redact`); repository secret scan: the `security` job in `.github/workflows/ci.yml` runs gitleaks 8.28.0 (pinned, checksum verified) over the full history with `.gitleaks.toml`, and fails when it scans zero commits (local baseline 2026-10-17: 453 commits, no findings after one fixture allowlist entry; green on PR #4, [run 39032815905](https://github.com/thanhnc261/e-agent/actions/runs/39032815905), 2026-10-17) | [I] |
| PR-26 | Run data is classified, minimized toward models, exported by class, retained and deletable | Field and record classes; route data boundary; purge keeps the audit skeleton | DR-05; ADR 0030 | none | Field and record classes (Phase 3 Task 3b.3): an unmarked property counts as `personal` (`test_unmarked_property_counts_as_personal`, `tests/unit/contracts/test_data_classes.py` and `tests/unit/kernel/test_registry_data_classes.py`); a data class instance path that resolves to no property fails admission (`test_data_class_pointer_must_exist_in_schema`, `tests/unit/kernel/test_registry_data_classes.py`); a value's class is never lower than a declaration on its path or an ancestor, over randomized data shapes, printing its case count and failing on zero (`test_a_value_class_is_never_lower_than_any_declaration_above_it`, `tests/unit/contracts/test_data_classes.py`); every record kind each store keeps declares a record and a retention class, on both stores, printing its count and failing on zero (`test_every_store_record_kind_declares_a_class`, `tests/conformance/test_record_classes.py`); readiness reports unmarked counts (`test_readiness_reports_unmarked_counts`, `tests/unit/server/test_api.py`). Minimization toward models (Task 3d.2): the assembler masks values by class and route and logs each mask (`test_personal_value_masked_on_hosted_route_and_logged`, `test_undeclared_dict_keys_do_not_leak_on_hosted_route`, `test_local_route_keeps_personal_values`, `test_finding_and_read_error_text_masked_on_hosted_route`, `test_finding_message_rendered_from_inventory_on_hosted_route`, `tests/unit/kernel/test_context_assembler.py`); its use on the model path lands in Tasks 3d.4 and 3d.5. Class-aware export (Phase 5), retention and deletion (Phase 7) have **none** | [Pa] |
| PR-27 | Every API route carries an authorization dependency | Session today, capability grants in Phase 7 | Adoption review XA-12 | none | **none** | [Pa] |

## Evidence and verification

| ID | Principle | In practice | Decided in | ENG | Check | Status |
|---|---|---|---|---|---|---|
| PR-28 | No hidden reasoning is persisted | Thinking parts stripped before storage, events, evidence and telemetry | AGENTS.md; ADR 0004 | ENG-EVID-3 | `test_no_hidden_reasoning_reaches_the_ledger` (`tests/unit/server/test_pydantic_driver_e2e.py:123`); `test_strip_thinking_removes_only_thinking_parts` (`tests/unit/adapters/pydantic_ai/test_driver_unit.py:43`) | [I] |
| PR-29 | Fixture and live results are reported separately; every failure, skip and blocker is named | Reports carry their environment | AGENTS.md | ENG-EVID-2 | The release report labels `"environment": "fixture"` (`scripts/release_report.py`); the rest is review | [Pa] |
| PR-30 | Store behaviour passes on both stores | Memory and PostgreSQL | Target §4; roadmap rule 1 | ENG-STORE-1 | `pg` gate; `tests/conformance/test_run_store.py` with `E_AGENT_TEST_STORE=postgres` | [I] |
| PR-31 | A gate fails on empty input and prints its count | No vacuous pass | Adoption review XA-04 | ENG-EVID-4 | `test_release_report_fails_on_zero_cases` (`tests/conformance/test_release_report.py`); `test_every_recording_is_replayed` (`tests/unit/server/test_recorded_model_replays.py`) closes the replay `TASKS` constant, the last entry on the ENG-EVID-4 silent-pass list | [I] |
| PR-32 | A change to the driver, prompts or tool schemas runs the replay suite | Prompts are code | Adoption review XA-17 | ENG-EVID-5 | `test_base_instructions_match_golden` (`tests/unit/adapters/pydantic_ai/test_prompt_golden.py`) pins the driver base instructions to a golden file; `tests/unit/server/test_recorded_model_replays.py` replays every recording and `test_every_recording_is_replayed` fails on an unreplayed one. Both run in every `pytest` run, so every change meets them in the `full` gate | [I] |

## Knowledge

| ID | Principle | In practice | Decided in | ENG | Check | Status |
|---|---|---|---|---|---|---|
| PR-33 | Ontology belongs to domain packs, engines to adapters, and there is one rule inventory | Every rule declares its enforcement engine | AGENTS.md; ADR 0009 | none | `test_rule_inventory_lists_every_rule_with_an_engine` (`tests/unit/plugins/erp/domain/test_procurement.py:155`); `test_rule_inventory_matches_shapes` (`tests/integration/test_procurement_rules.py:226`) | [I] |
| PR-34 | Untrusted content is data; facts come from structure or people, and model output only creates candidates | Retrieved text, tool output and memory never become instructions or approved facts; fact-source mode is reported | AGENTS.md; target §7.2 rule 5, §9; owner D-2 | ENG-TRUST-1 | Untrusted text in the model's context is fenced as data, over threat T1's injection fixtures (`tests/unit/kernel/fixtures/injection/`), and no value can close the fence (`test_untrusted_values_are_fenced`, `test_fence_cannot_be_closed_from_inside`, `tests/unit/kernel/test_context_assembler.py`; Phase 3 Task 3d.2, ADR 0032 §4). With `context_assembler: on`, a run over those injected fixtures proposes the same action over the same tool set as a run over clean values, and no injected text reaches the dynamic suffix (`test_injected_fixture_run_proposes_the_same_action`, `tests/unit/kernel/test_context_on.py`; Phase 3 Task 3d.5, with a scripted driver only, so it proves the kernel-side invariants, not a live model's behaviour). Candidate-only model facts and the fact-source mode report have **none** | [Pa] |

## Process and boundaries

| ID | Principle | In practice | Decided in | ENG | Check | Status |
|---|---|---|---|---|---|---|
| PR-35 | Plan first, design first; a contract change needs an accepted ADR; code and design never drift silently | Phase plans in `docs/plans/`; ADRs in `docs/adr/` | Roadmap rules 1–2 | ENG-PLAN-1, -2, -3 | `uv run e-agent-harness validate-context` for the plan; ADR status and drift are review only | [Pa] |
| PR-36 | Only the sandbox and e-agent's own containers are touched; protected paths stay protected | `odoo-bench` never; `archive/**` read-only | Roadmap rule 5; AGENTS.md | ENG-BOUND-1, -2 | Deny rules in `.claude/settings.json`; `harness/context.toml`; `uv run e-agent-harness check-scope` | [I] |
| PR-37 | Configuration is typed; code does not read `os.environ` directly | `server/environment.py` is the one reader | Adoption review XA-14 | ENG-ARCH-6 | Ruff TID251 bans `os.environ` and `os.getenv` under `src/e_agent` (`uv run ruff check .`); `tests/conformance/test_banned_api.py` proves the ban fires, that no file under `src/` is exempt, that the exemptions are line-level `# noqa: TID251` pinned by file and banned API (the two reader files), and that those files still flag a new `asyncio.create_task`; the helper's tests are in `tests/unit/server/test_environment.py` | [I] |
| PR-38 | Background tasks are supervised | No bare `asyncio.create_task` | Adoption review XA-15 | ENG-ARCH-7 | Ruff TID251 bans `asyncio.create_task` under `src/e_agent` (`uv run ruff check .`); `test_create_task_banned_in_product_code` proves the ban fires, `test_banned_api_allowlist_is_pinned` pins the one line-level exemption (the call in `src/e_agent/sdk/tasks.py`) and `test_allowed_files_still_ban_the_other_api` proves that file still flags `os.environ` (`tests/conformance/test_banned_api.py`); the helper's tests `test_supervised_task_failure_is_logged_and_reraised_on_await` and `test_supervised_task_cancel_is_not_logged_as_failure` are in `tests/unit/sdk/test_tasks.py`; an awaited kernel call passes `log_failure=False` and `tests/unit/kernel/test_timed_logging.py` proves a handled call failure is not logged | [I] |
| PR-39 | CI scans for secrets and vulnerable dependencies | Required checks | Adoption review XA-16 | ENG-BOUND-3 | The `security` job in `.github/workflows/ci.yml`: `pip-audit` 2.9.0 over the exported lock and `pnpm --dir ui audit --prod`, each failing on zero packages audited and on any finding (local baseline 2026-10-17: 72 Python packages and 28 UI packages, no findings); green on PR #4, [run 39032815905](https://github.com/thanhnc261/e-agent/actions/runs/39032815905), 2026-10-17; "required" depends on the owner setting branch protection | [Pa] |

## AGENTS.md section → rows

| AGENTS.md section | Rows |
|---|---|
| How work is done (roadmap rules 1–5) | PR-14, PR-22, PR-23, PR-35, PR-36 |
| Architecture rules | PR-01 – PR-06, PR-08, PR-09, PR-11, PR-12 |
| Execution and data integrity | PR-10, PR-13 – PR-21, PR-24, PR-26, PR-27, PR-40 |
| Plugins and knowledge | PR-07, PR-25, PR-33, PR-34 |
| Development and verification | PR-05, PR-25, PR-28 – PR-32, PR-37 – PR-39 |
| Environment boundaries | PR-36 |
| Principles; Documentation and completion | All rows (they point here); "a new principle is recorded as a row" has no row of its own and is enforced by review |

## Backlog: principles without a check

| Row | Missing check | Where it lands |
|---|---|---|
| PR-12, PR-13 | Model cannot choose a connection or mark a plan verified | Phase 2 Tasks 2c.6 and 2c.9 |
| PR-16 | Guardrail modification rule | First guardrail ADR |
| PR-20 | Effect declarations and live refusal | Phase 2 Tasks 2c.1, 2c.2 (ADR 0029) |
| PR-21, PR-26 | Bounded-result markers per capability; class-aware export; retention and deletion | Phase 3 landed the context markers and minimization (Task 3d.2) and the field and record classes (Task 3b.3; ADRs 0030, 0032); markers per capability and export in Phase 5; retention and deletion in Phase 7 |
| PR-40 | Startup refuses auto-approve outside a benchmark profile, above `write_low` or with a defaulted declaration | Phase 5 evaluation, after ADR 0029 declarations exist (ADR 0024) |
| PR-22, PR-23 | Toggle tests (default `off`, shadow cost, fallback boundary, readiness) | Phase 2 Part 2b (ADR 0027) |
| PR-27 | OpenAPI route enumeration test | Before Phase 7 (XA-12) |
| PR-34 | Candidate-only model facts; the fact-source mode report; the injection outcome test with a live model | The injection outcome test landed in Phase 3 Task 3d.5 for the scripted driver only (the fixtures and fence tests in Task 3d.2, ADR 0032); no roadmap phase or plan yet names the live-model run; the rest with the knowledge service (roadmap Phase 9, conditional) |
| PR-04, PR-06, PR-11 | Review-only by nature | No machine check planned; reviewers cite the row |
