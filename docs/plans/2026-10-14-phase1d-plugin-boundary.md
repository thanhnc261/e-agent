# Phase 1d: Plugin Boundary and Reusable Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft 2026-10-14 (revision 2, after the owner's comments on D1 and D2; revision 3, 2026-10-15, folds in adoption review XA-02 and XA-03 at Task 1d.7). **Approved by the owner on 2026-10-15** (revision 3), with D1–D6 at their defaults. ADR 0026 still passes owner gate G1 before Parts B and C.

**Goal:** make the core reusable on its own and make every plugin live where its folder says it is one. Concretely:
- the core (`contracts`, `sdk`, `kernel`, `server` and the infrastructure adapters) installs, starts and passes its tests with no ERP package present;
- ERP is the first plugin area under `src/e_agent/plugins/erp/`, with room for many ERP providers.

**Architecture:**

```text
src/e_agent/
├── contracts/  sdk/  kernel/  server/        core: domain-neutral, reusable for other agentic products
├── adapters/                                 infrastructure ports wired by bootstrap (not plugins yet)
│   └── postgres/  pydantic_ai/  shacl/  secretstore_local/
└── plugins/                                  namespace: discovered plugins only (no __init__.py)
    └── erp/                                  namespace: the ERP area (no __init__.py)
        ├── domain/      e_agent.plugins.erp.domain      dist domain-erp            (procurement, inventory, sales, crm, receivables)
        ├── odoo/        e_agent.plugins.erp.odoo        dist adapter-odoo          (plugin id odoo19)
        ├── simulator/   e_agent.plugins.erp.simulator   dist adapter-erp-simulator (plugin id fixture-erp; new)
        └── (sap/, dynamics/, … later: siblings of odoo)
```

Why this shape:
- **`plugins/erp/` is a namespace directory and not a package.** `src/e_agent/erp/` is a regular package today. If `odoo` were nested inside it, the shared `dists/_hooks` sub-tree hook would put Odoo into the `domain-erp` wheel, and the two distributions would no longer be independent. With a namespace directory, the domain pack and each provider are sibling packages and stay separately releasable.
- **Many ERP providers.** A new ERP system is a new sibling of `odoo/`. It imports only the public API of `e_agent.plugins.erp.domain`, never a sibling provider. The simulator is the first second provider, so the rule is exercised from day one.
- **Other enterprise areas** follow the same pattern (`plugins/<area>/domain`, `plugins/<area>/<provider>`). A vendor that spans areas (Odoo for HR later) stays filed under its first area and binds the other area's domain through its public API. ADR 0026 records this filing rule; it is not solved now.
- **Plugins are guests.** A plugin imports only contracts, the SDK and its area's public domain API. It never imports the kernel, the server, the store, the secret store or another infrastructure adapter, and credentials reach it only through `PluginServices`. A named import-linter contract enforces it, and a conformance test keeps every plugin package inside that contract (Task 1d.7; adoption review XA-02, PR-08).
- **The core never imports `e_agent.plugins`.** One import-linter contract enforces it. A packaging check proves it: the core wheels install and the server starts in a clean environment without any ERP wheel.

The phase has four parts:
- **A (decision gate):** ADR 0026.
- **B (core neutrality, no move yet):** manifest-driven auth and sandbox probe; task presets and the scripted driver contributed by the domain pack; the ERP simulator as a discovered provider plugin; the default profile out of the server; server dependencies narrowed; an ERP bundle distribution; the boundary locked.
- **C (layout):** the domain pack and Odoo move under `plugins/erp/`, with one re-pin.
- **D (verification).**

Run behaviour does not change.

**Tech Stack:** uv workspace, hatchling with the shared `dists/_hooks/src_tree.py` hook, import-linter, mypy, ruff, pytest, `scripts/repo_move.py` (extended), `scripts/plugin_inventory.py`, `scripts/check_wheels.py`, a new `scripts/check_core_only.py`.

**Spec:**
- The owner's acceptance of ADR 0026, 2026-10-15, with the amendment "plugins need a common SDK": contracts and the SDK are the common base, and the SDK gains shared provider helpers (connection spec in 1d.2, HTTP helper in 1d.7b).
- The owner's comments, 2026-10-14:
  - "If it is a plugin, it belongs in a plugins folder."
  - D1: "`plugins/erp/odoo`; think further: there may be many ERP providers."
  - D2: "e-agent is for enterprises, not only ERP, and its core may later be used to build other agentic products."
- Independent review of Phases 0–1, 2026-10-14 (reviewer subagent, fresh context): findings R-1 to R-8. Task 1d.1 records them.
- [Roadmap](../roadmap.md): the Phase 1 row and rules 1, 2 and 5. The [Phase 1 plan](2026-10-12-phase1-structure-refactor.md): layout decision 2026-10-12 (group by layer, no repeated folder names). The Phase 1 [handoff](../handoffs/2026-10-13-phase1-structure.md).
- [HLD](../design/high-level-design.md) §4 (plugins, distributions, bootstrap). [Target architecture](../design/target-architecture.md) §15 and §16, and the R3 row. AGENTS.md "Architecture rules" and "Repository map".
- ADR 0002: domain, capability, binding and connection are separate; multiple valid bindings are allowed; ambiguous routing is an error. ADR 0012 item 1: manifests declare the auth methods and `test_connection`.
- [X-agent adoption review](../reviews/2026-10-14-x-agent-adoption-review.md), approved 2026-10-14: XA-02 (a named "Plugins are guests" contract) and XA-03 (the registry enforces declared capability requirements), both at Task 1d.7. Principles PR-08 and PR-10 in [principles](../design/principles.md).
- [Design-principles review](../reviews/2026-10-14-design-principles-review.md) DR-03 (the manifest `connection` section is consumed; pulled forward from Phase 5) and DR-04 (fixture wiring belongs behind a plugin; the R3 row should be stated precisely). The review file was uncommitted at the time of writing.

## Global Constraints

- **Run behaviour unchanged.**
  - Every run's event stream, action records, digests and outcomes stay the same.
  - The OpenAPI document does not change (`uv run python scripts/export_openapi.py --check`).
  - The CLI demo prompts match the golden file (Task 1d.3).
- **Named interface and packaging changes.** These are the only allowed changes, and ADR 0026 owns them:
  1. The server package no longer ships a default profile. `load_profile()` needs a path or `E_AGENT_PROFILE`. The ERP fixture profile ships with the simulator plugin (Task 1d.6).
  2. `e-agent-server` no longer depends on `e-agent-domain-erp` or `e-agent-adapter-odoo`.
  3. Two new distributions: `e-agent-adapter-erp-simulator` (code) and `e-agent-erp` (a bundle without code that installs the ERP product).
  4. The public import names of the domain pack and the Odoo adapter change in Task 1d.10.
  5. Two profile-schema changes: `DriverConfig.task_kind` becomes `str`, validated against the admitted task presets (Task 1d.3); `DriverConfig.demand_ref` and `product_ref` fold into `refs`, and the loader moves the two old keys into `refs` so existing profiles keep loading (Task 1d.4).
  6. The common plugin SDK: `e_agent.sdk.connection` (1d.2) and `e_agent.sdk.http` behind the optional extra `e-agent-plugin-sdk[http]`, with one `ignore_imports` entry `e_agent.sdk.http -> httpx` in the core import contract (1d.7b).

  The existing ten distribution names and versions stay.
- **Verbatim moves.** Moves use `git mv`, so git shows renames. File contents change only where a module path is embedded (ENG-WORK-2).
- **Namespace packages.** No `__init__.py` is added to `src/e_agent/`, `src/e_agent/adapters/`, `src/e_agent/plugins/` or `src/e_agent/plugins/erp/` (ENG-ARCH-5).
- **Pins.** No committed test asserts a plugin digest (checked 2026-10-14), so intermediate digest changes in 1d.3–1d.6 break nothing. The final pins of `domain-erp`, `odoo19` and `fixture-erp` are recorded once, in Task 1d.10, and the owner re-pins the local live profile once, in Task 1d.12.
- **Ordering with Phase 2.** This phase runs before Phase 2. At this phase's close, the [Phase 2 plan](2026-10-14-phase2-execution-ir.md) is amended for the new paths, and its Task 2c.2 builds on the task presets from Task 1d.3 (ENG-PLAN-3). The R-1 fix replaces the "manifest `connection` consumed" item of the [Odoo tools plan](2026-10-12-odoo-tools-from-erp-bench.md) (DR-03); that plan drops the item at this phase's close.
- **Harness.**
  - Features `F-1d-1` … `F-1d-12` and `F-1d-7b` are in `harness/state/1/features.json` (decision D6).
  - One contract per task, `check-scope` before each commit, gate evidence after the commit, `close-check` before a task closes.
  - Tasks that edit a digest input (1d.1 the ADR index; 1d.8 `harness/context.toml`; 1d.10 AGENTS.md, the roadmap and the designs; 1d.11 the roadmap) run `uv run e-agent-harness refresh-task` before `close-check` (G-7).
- **Branch:** `refactor/phase1d-plugin-boundary` from `main`.
  - Stage explicit paths.
  - Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
  - Merge, push and rebase only on the owner's instruction.
- **Boundaries.**
  - Containers: `e-agent-ledger` (test database `e_agent_test`) for the Postgres run. `odoo19-learning` and `e-agent-ledger` in the live check only. Never `odoo-bench` (ENG-BOUND-1).
  - `archive/**` and existing `research/**` reports stay unchanged (ENG-BOUND-2).
  - The secret profile `profiles/live-odoo19-learning.local.json` is re-pinned by the owner (Task 1d.12), never by an agent.

## Review Focus

These are failure modes that the happy-path tests do not exercise. Each one is pinned to the task that adds its test.

1. **The live sandbox guard weakens.** `LIVE_PROVIDERS_WITH_SANDBOX` is a safety check: it verifies the synthetic sandbox identity before live work. Once manifests drive it, a live provider whose manifest declares no sandbox probe must make startup refuse; skipping the check is not allowed. Test: Task 1d.2 `test_live_provider_without_sandbox_probe_refuses_startup`.
2. **Credentials go somewhere else.** The auth placement read from the manifest must equal today's (`Authorization`, prefix `bearer `). An unknown placement is refused, never defaulted. Tests: Task 1d.2 `test_odoo_auth_placement_from_manifest_equals_previous` and `test_unknown_auth_placement_refused`.
3. **Simulator code reached from a live composition.** A profile that does not enable `fixture-erp` never imports the simulator package. Test: Task 1d.5 `test_live_profile_never_imports_simulator` (subprocess, `sys.modules`).
4. **Two ERP providers route ambiguously** (ADR 0002; `PluginRegistry.resolve`). Odoo and the simulator are both installed:
   - one of them enabled: composes;
   - both enabled, each with its own connection: admitted, and each binding resolves to its own executor;
   - two bindings of one contract on the same connection: resolution is refused with `CONFLICT`, never chosen;
   - a duplicate binding id: refused at startup.

   Test: Task 1d.5 `test_two_erp_providers_routing`.
5. **The core still needs ERP.** The core wheels must install and the server must start without any ERP wheel. Test: Task 1d.8 `scripts/check_core_only.py`.
6. **A caller still relies on the packaged default profile.** Test: Task 1d.6 `test_load_profile_requires_path_or_env`, and every existing caller migrated (a grep test for `load_profile()` without arguments).
7. **A namespace directory gains an `__init__.py`**, which would change the import root and, through the hook, the pins. Test: Tasks 1d.5 and 1d.10, which extend `tests/conformance/test_repo_layout.py::test_e_agent_stays_a_namespace_package` to `plugins/` and `plugins/erp/`.
8. **Stale module strings outside Python imports.** Entry-point values, the manifest `factory`, `check_wheels.py` (`files('e_agent.erp')`), `scripts/odoo_sandbox.py`, `scripts/qualify_model.py` and the docs all embed module paths. Test: Task 1d.10 `test_no_old_plugin_module_paths_remain` and `uv run python scripts/repo_move.py check --docs`.
9. **A plugin escapes the guest contract.** A new provider package is added but not listed in the contract, so import-linter never checks it and the gate stays green. Test: Task 1d.7 `test_every_plugin_package_is_a_guest`, which derives the plugin packages from the installed `e_agent.plugins.v1` entry points rather than from a hand-kept list.
10. **A declared requirement is never checked.** `CapabilityDescriptor.required_features` is declared and never read today, so a binding that lacks a required feature is admitted and fails, if at all, at call time. Test: Task 1d.7 `test_binding_missing_required_feature_refused`.
11. **The HTTP helper leaks or wanders.** It must never log or echo a header or a body, and must refuse any host other than the connection's base-URL host. Tests: Task 1d.7b `test_http_never_echoes_credentials` and `test_http_refuses_other_hosts`.
12. **A plugin depends on more than the common base.** Test: Task 1d.7b `test_plugin_dependencies_are_the_common_base`.

## Design refs

| Document | Section | Change |
|---|---|---|
| `docs/design/high-level-design.md` | §4 | Core versus plugin areas; which packages are entry-point plugins; the ERP bundle (1d.10) |
| `docs/design/target-architecture.md` | §15, §16; R3 row | New tree. R3 is stated precisely: "[I] for domain packs and provider adapters; [P] for drivers, stores, validators and secret stores" (DR-04) (1d.10) |
| `docs/design/mvp-detailed-design.md` | §3 package list | New paths and distributions (1d.10) |
| `.agents/skills/eng-foundations/references/rules.md` | ENG-ARCH-1, ENG-ARCH-5 | New plugin paths; the core-never-imports-plugins rule (1d.10) |
| `AGENTS.md`, `README.md` | Purpose, Repository map, Development and verification | A domain-neutral core with ERP as the first plugin area; namespace rule for `plugins/`; the profile now has to be given (1d.10) |
| `docs/adr/0012-schema-driven-integration-management.md` | item 1 | Consumed by bootstrap (1d.2); no text change |
| `docs/design/principles.md` | PR-08, PR-10 and the backlog table | The check column names the new contract and tests; status [I]; backlog rows removed (1d.11) |

## ADRs

| ADR | Decision | Status | Effect |
|---|---|---|---|
| 0026 (1d.1; accepted 2026-10-15 with the common-SDK amendment) | Plugin layout and a reusable core. It covers: the tree above and its namespace rule; the core never imports `e_agent.plugins`; providers import only their area's domain API, never a sibling; the filing rule for vendors that span areas; the named "Plugins are guests" contract and the registry check of declared capability requirements (XA-02, XA-03); the simulator as a discovered provider; task presets and the scripted driver contributed by the domain pack; server dependencies narrowed and the `e-agent-erp` bundle; no default profile in the server | Accepted | Parts B and C may start |
| 0002 | Capability naming and domain packs | Accepted | Unchanged; Review Focus 4 tests its routing rule with two providers |
| 0012 | Schema-driven integration management | Accepted | Item 1 becomes true in code (1d.2) |

**Owner decisions** (default applies if no answer):

| Id | Decision | Default |
|---|---|---|
| D1 | The tree above: `plugins/erp/{domain, odoo, simulator, …}`, where `plugins/` and `plugins/erp/` are namespace directories | As drawn |
| D2 | The fake ERP used for tests (`FakeErp`, its scenarios, plugin id `fixture-erp`) ships today inside the real ERP domain package and is wired into the server by hand. It becomes its own discovered provider plugin, `plugins/erp/simulator`. A fixture profile enables it the same way a live profile enables `odoo19`. The scripted driver stays with the domain pack, because live smoke tests use it with Odoo too | As described |
| D3 | `e-agent-server` drops its ERP dependencies; the new bundle `e-agent-erp` installs the server plus the ERP plugins | As described |
| D4 | The server ships no default profile; `--profile` or `E_AGENT_PROFILE` is required | As described |
| D5 | Phase 1 bookkeeping. R-5: the research links are ruled "stay broken" (research is create-only). R-6: the handoff gets a dated follow-up note. R-8: HP-6 is carried to the harness backlog (H5) | As described |
| D6 | Feature list location | Appended to `harness/state/1/features.json` as `F-1d-*` |

## Toggles and fallback

No runtime feature is added, so there is no toggle and no fallback: roadmap rule 3 applies to new runtime features. The phase changes structure, packaging and how a profile is located. Run behaviour equality is shown by:
- the unchanged OpenAPI document;
- the golden CLI prompts (1d.3);
- the unchanged test suite;
- the core-only check (`core` set, 1d.8);
- the live check (1d.12).

## Gate

| Task | Gate set |
|---|---|
| 1d.1 | `full` (docs only) |
| 1d.2–1d.4, 1d.6, 1d.7, 1d.9 | `full` |
| 1d.5, 1d.7b | `full` and `uv run python scripts/check_wheels.py` |
| 1d.8 | `full`, `core` and `uv run python scripts/check_wheels.py` |
| 1d.10 | `full`, `pg`, `e2e`, `core` and `check_wheels.py` |
| 1d.11 | end-of-phase levels 1–3 |
| 1d.12 | level 4 (live) |

The gate commands come from `harness/context.toml`:
- `full`: `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run python scripts/export_openapi.py --check`, `uv run pytest -q`, `pnpm --dir ui gen:check`, `pnpm --dir ui check`.
- `pg`: `E_AGENT_TEST_STORE=postgres uv run pytest -q tests/unit/kernel`, with `E_AGENT_TEST_PG_DSN` pointing at `e_agent_test` (G-11).
- `e2e`: `make e2e`.

Task 1d.8 adds a `core` set in `harness/context.toml` (`uv run python scripts/check_core_only.py`); it joins `full` only if it is fast enough.

**End-of-phase levels** (`eng-verify`, in order, on a clean tree):
1. the `full` gate and the `core` set;
2. the Postgres run;
3. `make e2e`;
4. the live check.

## Live check

The owner runs it through `live-sandbox`, after re-pinning `profiles/live-odoo19-learning.local.json` with `scripts/plugin_inventory.py` from freshly built wheels.

It exercises:
- `/health/ready` with the live profile:
  - `domain-erp` and `odoo19` are admitted with the new pins;
  - `fixture-erp` is not loaded;
  - the sandbox marker check passes through the probe the manifest declares.
- Task 1, the read-only shortage question: it succeeds as before.
- A start with a deliberately wrong pin: it is refused.

It may not touch `odoo-bench`, any container outside `odoo19-learning-*` and `e-agent-ledger`, or live business data. No write task is needed, because no write path changes. Live keys expire 2026-10-19, so a later check needs renewed keys. Results are reported separately from fixture results (ENG-EVID-2).

---

## Part A: decision gate

### Task 1d.1: review record and ADR 0026

**Files:**
- `docs/reviews/2026-10-14-phase1-plugin-boundary-review.md`: the reviewer's R-1 to R-8 with evidence, plus what it did not run (full gate, full pytest, Postgres, e2e, wheel rebuild).
- `docs/adr/0026-plugin-layout-and-reusable-core.md`
- `docs/adr/README.md`

**Steps:**
- [ ] Write the review record from the reviewer's JSON.
- [ ] Write ADR 0026 (status Proposed) with every item in the ADRs table above. Include the alternatives that were considered and rejected:
  - a flat `plugins/erp` + `plugins/odoo`;
  - `domains/erp` only;
  - a top-level `plugins/<name>/` tree with its own `src/`, which contradicts the 2026-10-12 decision;
  - nesting providers inside the domain package, which breaks wheel independence.
- [ ] Add the index row. Run `uv run python scripts/repo_move.py check`. Expected: no new broken links.
- [ ] Commit `docs(adr): 0026 plugin layout and reusable core; Phase 0-1 review record`.

**Owner gate G1:** the owner accepts or amends ADR 0026 and answers D1–D6. Parts B and C start after that.

---

## Part B: core neutrality, no move yet

### Task 1d.2: auth placement and sandbox probe from manifests (R-1)

**Files:**
- `src/e_agent/sdk/connection.py`: typed models for the manifest `connection` section (auth methods with placement, sandbox probe). An unknown placement fails validation; a manifest without a `connection` section is valid (ADR 0026, common plugin SDK).
- `src/e_agent/server/bootstrap.py`: remove `AUTH_PLACEMENT` and `LIVE_PROVIDERS_WITH_SANDBOX`, and read `manifest.connection` of the admitted plugins through `e_agent.sdk.connection`.
- `src/e_agent/kernel/registry.py`: expose the admitted manifests' `connection` sections, if they are not reachable yet.
- `tests/unit/server/test_manifest_connection.py`

**Steps:**
- [ ] Write the failing tests:
  - `test_odoo_auth_placement_from_manifest_equals_previous`
  - `test_unknown_auth_placement_refused` (`STARTUP_REJECTED`)
  - `test_second_provider_wired_without_server_edit`
  - `test_live_provider_without_sandbox_probe_refuses_startup`
  - `test_live_odoo_sandbox_check_unchanged`
- [ ] Run `uv run pytest -q tests/unit/server/test_manifest_connection.py`. Expected: the new tests fail; the second-provider test fails with a `KeyError` from `AUTH_PLACEMENT`.
- [ ] Implement.
- [ ] Run the same command and `uv run pytest -q tests/unit/server`. Expected: pass.
- [ ] Commit `refactor(server): auth placement and sandbox probe from adapter manifests`.

### Task 1d.3: task presets from the domain pack (R-3)

**Files:**
- `src/e_agent/sdk/ports.py`: add `PluginContribution.task_presets: tuple[TaskPreset, ...]`. `TaskPreset` holds the kind, the demo prompt with its default refs written out, the default refs in the order overrides apply, and the help text. Rendering replaces defaults one override after another, exactly as the CLI did, so the prompts stay unchanged even when an override equals another ref's default (review R-1). Phase 2 Task 2c.2 extends these into task definitions.
- `src/e_agent/erp/plugin.py`: the eight presets, which today are `TASK_PROMPTS` in `cli.py`, and `TASK_KINDS` and `DEFAULT_REFS` in `erp/testing/scripted_tasks.py`.
- `src/e_agent/server/profile.py`: `DriverConfig.task_kind: str = "draft-po"`; remove the ERP wording from the field docs.
- `src/e_agent/kernel/registry.py`: collect the presets by kind; two plugins that define one kind differently are refused at startup (PR-09).
- `src/e_agent/server/bootstrap.py`: validate `task_kind` against the admitted presets.
- `src/e_agent/server/cli.py`: prompts come from the presets. `--task` has no static choices, because the parser is built before admission; bootstrap refuses an unknown kind and names the admitted ones.
- `tests/unit/server/test_task_presets.py`
- `tests/unit/server/golden/demo_prompts.json`, written by `tests/unit/server/record_demo_prompts.py`.

**Steps:**
- [ ] On unchanged code, run `uv run python tests/unit/server/record_demo_prompts.py`. Commit the golden file before any other change.
- [ ] Write the failing tests:
  - `test_cli_demo_prompts_unchanged`
  - `test_unknown_task_kind_refused_at_startup`
  - `test_profile_accepts_non_erp_task_kind_string`
  - `test_task_kind_choices_come_from_presets`
- [ ] Run `uv run pytest -q tests/unit/server/test_task_presets.py`. Expected: fails with `AttributeError: task_presets`.
- [ ] Implement.
- [ ] Run the same command and `uv run python scripts/export_openapi.py --check`. Expected: pass, no change.
- [ ] Commit `refactor(server): task presets come from the domain pack`.

### Task 1d.4: the scripted driver contributed by the domain pack (R-2, part 1)

**Files:**
- `src/e_agent/sdk/ports.py`: `PluginContribution.driver_factories: Mapping[str, DriverFactory]`, keyed by `driver.kind`. A `DriverFactory` takes a `DriverRequest` (connection id, mode, task kind, refs) and returns an `AgentDriver`. The scripted driver needs those profile arguments, so contributed instances (`drivers`) are not enough; `drivers` stays (ADR 0026).
- `src/e_agent/erp/plugin.py`: contributes the `scripted` driver factory.
- `src/e_agent/server/bootstrap.py`: `driver.kind == "scripted"` resolves through the registry. No `ScriptedErpDriver` import remains, and the `demand:d-001` and `product:widget-a` defaults come from the task preset.
- `src/e_agent/server/profile.py`: `DriverConfig.demand_ref` and `product_ref` fold into `refs` under the same keys; the loader moves the two old top-level keys into `refs`, so existing local profiles keep loading (ADR 0026). `refs.demand_ref` is not read before this task (`cli.demo_prompt` skips it, as the old CLI did); folding the key removes that skip, and the golden's `refs-demand` cases change on purpose, re-recorded in the same commit. Ruling (1d.4): an old key that differs from its `refs` entry is refused at load, never resolved; an equal one is the same setting. The 1d.3 golden pinned both resolutions (`legacy+refs`: the old key won; `legacy-default`: `refs` won), which no single fold keeps, so `legacy-default` leaves the golden for a refusal test and `legacy+refs` uses equal values, the live check's form.
- `tests/unit/server/test_driver_factories.py`

**Steps:**
- [ ] Write the failing tests:
  - `test_scripted_driver_resolved_from_registry`
  - `test_scripted_driver_runs_against_any_enabled_erp_provider` (fixture now; Odoo in the live check)
  - `test_unknown_driver_kind_refused`
  - `test_old_ref_keys_move_into_refs`
- [ ] Run `uv run pytest -q tests/unit/server/test_driver_factories.py`. Expected: fails (no factory seam).
- [ ] Implement.
- [ ] Run the same command and `uv run pytest -q`. Expected: pass.
- [ ] Commit `refactor(server): scripted driver comes from the domain pack`.

### Task 1d.5: the ERP simulator as a discovered provider plugin (R-2, part 2; D2)

**Files:**
- `src/e_agent/plugins/erp/simulator/`: created here, at its final place. It holds the simulator from `src/e_agent/erp/testing/fake_erp.py` and `scenarios.py`, moved with `git mv`, plus `plugin.py` and `e_agent_plugin.json` (plugin id `fixture-erp`). The settings are `scenario` and `lose_response_after_commit`. Until 1d.10 it imports the domain through `e_agent.erp`.
- `dists/adapter-erp-simulator/pyproject.toml`: entry point `fixture-erp`; depends on contracts, the SDK and `domain-erp`.
- `src/e_agent/server/bootstrap.py`: no fixture registration and no `FakeErp`. `Runtime.fake_erp` is gone. The CLI's create-call report reads a provider-neutral diagnostics hook.
- `src/e_agent/server/cli.py`: `--scenario` sets the simulator setting.
  Ruling (1d.5): the CLI cannot name `fixture-erp` (1d.7 forbids `erp` in the server), so `--scenario` and `--fault lost-response` set the `scenario` and `lose_response_after_commit` settings of every enabled plugin whose profile entry names that setting, and are refused when none does. `build_runtime` takes `plugin_settings` by plugin id in place of `scenario` and `lose_response_after_commit`; settings for a plugin the profile does not enable are refused. `FixtureConfig.scenario` stays in the schema (no third profile-schema change; review R-2): the scenario is the plugin's setting, and a fixture profile's `fixture.scenario` follows the 1d.4 rule against it: equal to the setting of the enabled plugins that take `scenario` is one setting, a different value is refused at startup, and so is a value no enabled plugin takes (a profile written before 1d.5 loads, then startup names the missing simulator). The JSON key `fixture_erp_create_calls` becomes `provider_diagnostics`, filled from a `diagnostics` hook on `PluginContribution`, so `fake_erp.py` changes only in its import lines. A factory's `InvalidPluginSettings` (an unknown scenario) is refused at admission with `STARTUP_REJECTED`; it was `INVALID_REQUEST` from bootstrap. The exception carries the setting's name and a fixed reason, and the registry composes the message, so no setting value reaches it (review R-1). Discovery walks namespace parents by their last name, because a dotted lookup of `e_agent.plugins.erp` fails in a fresh process.
- the fixture profile: enables `fixture-erp`.
- `pyproject.toml`: an import-linter root package for the simulator; providers are independent of each other.
- `tests/unit/plugins/erp/simulator/`, `tests/conformance/test_repo_layout.py`

**Steps:**
- [ ] Write the failing tests:
  - `test_fixture_profile_composes_through_discovery`: same scenarios, same create-call count.
  - `test_live_profile_never_imports_simulator`
  - `test_two_erp_providers_routing`
  - `test_unknown_scenario_refused`
  - `test_plugins_dirs_are_namespace_packages`
- [ ] Run `uv run pytest -q tests/unit/plugins/erp/simulator tests/conformance/test_repo_layout.py`. Expected: fails (no plugin `fixture-erp` discovered).
- [ ] Implement.
- [ ] Run `uv run python scripts/plugin_inventory.py` for the new wheel and record its first pin.
- [ ] Run the same tests, `uv run pytest -q` and `uv run python scripts/check_wheels.py`. Expected: pass. The `domain-erp` wheel no longer contains `fake_erp.py` or `scenarios.py`.
- [ ] Commit `refactor: ERP simulator becomes a discovered provider plugin`.

### Task 1d.6: no default profile in the server (D4)

**Files:**
- `src/e_agent/server/profiles/fixture.json` moves (`git mv`) into the simulator package as a resource. A helper `fixture_profile_path()` returns its path.
- `src/e_agent/server/profile.py`: `load_profile(path=None)` reads `E_AGENT_PROFILE`, and otherwise raises a clear error.
- The callers that use the default today (about 25 in `tests/` and `scripts/`, including `scripts/release_report.py`, `scripts/qualify_model.py` and `scripts/capture_model_replays.py`): pass `fixture_profile_path()`.
- `Makefile`, `README.md`: commands pass the profile.
- `tests/unit/server/test_profile_location.py`

**Steps:**
- [ ] Write the failing tests:
  - `test_load_profile_requires_path_or_env`
  - `test_env_profile_is_used`
  - `test_no_caller_uses_the_implicit_default`: a grep over `src/`, `tests/` and `scripts/` for `load_profile()` without arguments.
- [ ] Run `uv run pytest -q tests/unit/server/test_profile_location.py`. Expected: fails (the default still loads).
- [ ] Implement and migrate the callers.
- [ ] Run `uv run pytest -q` and `make e2e`. Expected: pass.
- [ ] Commit `refactor(server): profiles are given, not packaged with the server`.

### Task 1d.7: lock the boundary and enforce declared requirements (XA-02, XA-03)

**Files:**
- `pyproject.toml`: two contracts.
  - "Core never imports plugins". It forbids `e_agent.contracts`, `e_agent.sdk`, `e_agent.kernel` and `e_agent.server` from importing the plugin packages (`e_agent.erp`, `e_agent.adapters.odoo` and `e_agent.plugins.erp.simulator` until 1d.10; `e_agent.plugins.*` after it). It replaces the per-package forbids on `e_agent.kernel`.
  - "Plugins are guests" (XA-02, PR-08). Its source modules are the same plugin packages. It forbids `e_agent.kernel`, `e_agent.server`, `e_agent.adapters.postgres`, `e_agent.adapters.secretstore_local`, `e_agent.adapters.pydantic_ai` and `e_agent.adapters.shacl`. Today the plugins import only `e_agent.contracts`, `e_agent.sdk` and the ERP domain API (checked 2026-10-15), so the contract holds from its first run; an unanchored grep for in-function imports found none either. The existing per-plugin contracts stay; this one gives the rule a name and covers every plugin package.
- `src/e_agent/kernel/registry.py`: `PluginRegistry.register()` refuses with `STARTUP_REJECTED` a binding template whose `supported_features` lacks any of its contract's `required_features`. The message names the binding, the contract and the missing features (XA-03, PR-10). No committed manifest declares features today (checked 2026-10-15), so no composition changes.
- `src/e_agent/kernel/proposals.py:230`: the docstring loses its ERP task ids (R-7).
- `tests/unit/server/test_generic_composition.py`, `tests/conformance/test_plugin_guests.py`, `tests/unit/kernel/test_registry.py`

**Steps:**
- [x] Write the failing tests:
  - `test_notes_pack_composes_through_bootstrap`: the non-ERP notes pack from `tests/unit/kernel/conftest.py`, registered through injected discovery, composes and runs a fixture read without importing any ERP package.
  - `test_server_has_no_domain_literals`: a grep over `src/e_agent/server` for `demand:`, `product:`, `odoo`, `erp` and `procure`. Import-linter cannot see string literals. (Ruling at 1d.7: the `"demand:d-001"` default had already left `bootstrap.py` in 1d.4; the old profile keys `demand_ref` and `product_ref`, an approved migration fold, match none of the patterns and stay. The `task_kind` default `"draft-po"` in `profile.py` matches none either and is left for the Phase 2 task definitions, because removing it is a profile-schema change not named in the Global Constraints.)
  - `test_every_plugin_package_is_a_guest`: reads the installed `e_agent.plugins.v1` entry points, takes the parent package of each entry point's module (`e_agent.adapters.odoo.plugin` → `e_agent.adapters.odoo`), and fails if any is not a source module of "Plugins are guests". It also fails when it finds no plugin at all, so it cannot pass on empty input.
  - `test_binding_missing_required_feature_refused`: a capability requiring `{"x"}` with a template that supports nothing is refused at registration with `STARTUP_REJECTED`.
  - `test_binding_with_required_features_admitted`: the same capability with a template supporting `{"x", "y"}` is admitted.
  - `test_binding_missing_required_feature_refused_without_a_connection`: the template is refused at registration even when no connection is assigned to it.
  - `test_capabilities_without_requirements_unchanged`: the fixture profile admits the same plugins and bindings as before. (Ruling at 1d.7: it lives in `tests/unit/server/test_generic_composition.py`, so the kernel tests stay free of ERP imports.)
- [x] Run `uv run pytest -q tests/unit/server/test_generic_composition.py tests/conformance/test_plugin_guests.py tests/unit/kernel/test_registry.py`. Expected: the guest test fails (no such contract), and the feature tests fail (the binding is admitted). Observed at 1d.7: the literal test fails too, on the demo help text in `cli.py` ("procurement"), which is reworded; the composition test passes on the existing tree.
- [x] Implement.
- [x] Run `uv run lint-imports` and the same tests. Expected: pass. To watch each contract fail, temporarily add `from e_agent.erp import plugin` to `bootstrap.py`, and then `import e_agent.adapters.postgres` to the simulator's `plugin.py`; restore both.
- [x] Commit `test: core never imports plugins; plugins are guests; required features enforced`.

Out of scope: probing a live instance for its features, and leaving a capability off the tool surface with a reason code when the instance lacks one. Both land in Phase 5 with the per-capability feature probe (adoption review XA-03).

### Task 1d.7b: common plugin SDK: authenticated HTTP helper (ADR 0026 amendment)

Runs after 1d.7, so the helper is written inside the guest contract, and before 1d.8, because the `plugin-sdk` wheel gains an optional extra.

**Files:**
- `src/e_agent/sdk/http.py`: an authenticated async HTTP helper built from an `AuthContext` and the connection's base URL. It:
  - applies the `AuthContext` to the request headers;
  - refuses a request whose host differs from the base-URL host;
  - raises a transport-level rejection for a 4xx response, with a code from the caller's allow-list (otherwise `REJECTED`) and a fixed safe message;
  - lets a 5xx, timeout or transport error propagate as ambiguous;
  - never logs or echoes a header or a response body.
- `src/e_agent/adapters/odoo/client.py`: `OdooJson2Client` uses the helper. Its allow-listed codes, the database header and the target context stay in the Odoo client; the executor's mapping to `KnownNoEffectError` is unchanged.
- `dists/plugin-sdk/pyproject.toml`: `[project.optional-dependencies] http = ["httpx>=0.28,<1"]`. `dists/adapter-odoo/pyproject.toml` depends on `e-agent-plugin-sdk[http]` and drops its direct `httpx` dependency.
- `pyproject.toml`: the contract "Core packages do not import agent frameworks or provider SDKs" gains `ignore_imports = ["e_agent.sdk.http -> httpx"]`, the one exemption ADR 0026 names.
- `tests/unit/sdk/test_http.py`, `tests/conformance/test_plugin_dependencies.py`

  Ruling (1d.7b): `PluginHttpClient` holds the base URL, timeout and transport, and takes the `AuthContext` per request (`post_json(auth, path, body, …)`): the Odoo plugin builds its client once at `create_plugin`, while an `AuthContext` covers one invocation. A 5xx, a redirect, a 2xx body that is not JSON, a timeout and a transport error raise the SDK's `HttpAmbiguous` instead of the raw httpx exception, because `httpx.HTTPStatusError` keeps the request and its credential header; every helper exception is raised outside the handler of the httpx error, so nothing chains to it. The executor maps any exception other than `KnownNoEffectError` to UNKNOWN, so this changes no outcome. A 4xx body that is not a JSON object now gives `REJECTED`; before, it raised an `AttributeError`, an ambiguous outcome. A path must start with a single `/`; a caller `Host` header is refused. Scope additions: `docs/design/principles.md` (PR-08 and PR-25 name the new checks) and `scripts/check_wheels.py` (the bare SDK wheel installs no httpx; the Odoo wheel imports its client through the extra).

**Steps:**
- [x] Write the failing tests:
  - `test_http_applies_auth_context`
  - `test_http_refuses_other_hosts`
  - `test_http_4xx_is_rejection_with_allowed_code`: an unknown code becomes `REJECTED`, and the provider body text never appears in the exception.
  - `test_http_5xx_and_transport_errors_are_ambiguous`
  - `test_http_never_echoes_credentials`: the secret appears in no log record and no exception text (capture logs at DEBUG).
  - `test_plugin_dependencies_are_the_common_base`: each plugin distribution (found from the `e_agent.plugins.v1` entry points in `dists/*/pyproject.toml`) depends on no e-agent distribution other than `e-agent-contracts`, `e-agent-plugin-sdk` and, for a provider, its area's domain pack. It fails when it finds no plugin.
  - `test_sdk_imports_httpx_only_in_http_module`: importing `e_agent.sdk` and every other SDK module leaves `httpx` out of `sys.modules` (subprocess).
- [x] Run `uv run pytest -q tests/unit/sdk/test_http.py tests/conformance/test_plugin_dependencies.py`. Expected: fails (no `e_agent.sdk.http`).
- [x] Implement, then move the Odoo client onto the helper.
- [x] Run `uv run pytest -q tests/unit/adapters/odoo tests/unit/sdk`, `uv run lint-imports` and `uv run python scripts/check_wheels.py`. Expected: pass; the Odoo client's existing tests are unchanged.
- [x] Commit `feat(sdk): authenticated HTTP helper for plugins; Odoo client uses it`.

### Task 1d.8: packaging for a reusable core (D3)

**Files:**
- `dists/server/pyproject.toml`: drop `e-agent-domain-erp` and `e-agent-adapter-odoo`.
- `dists/bundle-erp/pyproject.toml`: the new distribution `e-agent-erp`, with no code. It depends on the server and on the ERP domain, the Odoo adapter and the simulator.
- the root workspace config: add the new members.
- `scripts/check_core_only.py`:
  - builds the core wheels (contracts, plugin-sdk, kernel, server and the four infrastructure adapters);
  - builds a throwaway `core-test-pack` wheel from an inline notes-domain module, because `tests/unit/kernel/conftest.py` is not installable;
  - installs both into a fresh temporary venv without any ERP wheel;
  - starts the server with a profile that enables only the test pack, and calls `/health/ready`. The test pack contributes a task preset and the profile names it in `driver.task_kind`, because bootstrap refuses a kind that no admitted plugin offers (Task 1d.3).
- `harness/context.toml`: a new gate set `core` runs the script. The script also joins `full` if it finishes in under about a minute; otherwise it runs at the end of the phase and in CI.
- `tests/conformance/test_core_only.py`: the script's assertions are unit-tested on its helpers.

**Steps:**
- [x] Write the failing check: run `uv run python scripts/check_core_only.py`. Expected today: it fails while resolving the server wheel, because the server depends on `e-agent-domain-erp`. Time the run to decide whether it joins `full`.
- [x] Implement. Confirm the lock with `uv lock --check`; relock only for the new members and the narrowed dependencies, and show that third-party versions are unchanged (G-3).
- [x] Run the script, `uv run python scripts/check_wheels.py` and the `full` gate. Expected: pass.
- [x] Commit `build: core installs without ERP; e-agent-erp bundle`.

---

## Part C: layout

### Task 1d.9: mover support for the plugin layout

**Files:**
- `scripts/repo_move.py`: a `plugins` move set: `src/e_agent/erp` → `src/e_agent/plugins/erp/domain`, `src/e_agent/adapters/odoo` → `src/e_agent/plugins/erp/odoo`, with their tests and hook `package` values. It also rewrites module paths in imports, entry points, manifest `factory` values and module strings in scripts.
- `tests/conformance/test_repo_move.py`

**Steps:**
- [ ] Write the failing test `test_plugins_move_on_scratch_repo`. It covers: renames; rewritten imports, entry point and `factory`; no `__init__.py` in a namespace directory; `check` clean.
- [ ] Run `uv run pytest -q tests/conformance/test_repo_move.py -k plugins`. Expected: fails (unknown move set).
- [ ] Implement.
- [ ] Run the same command. Expected: pass.
- [ ] Commit `feat(scripts): mover support for the plugin layout`.

### Task 1d.10: run the move and re-pin (one commit)

**Files:**
- the domain pack and the Odoo adapter, with their tests, moved by `git mv`;
- the importing files outside them: the simulator, `scripts/check_wheels.py`, `scripts/qualify_model.py`, `scripts/odoo_sandbox.py`, and tests under `tests/integration`, `tests/unit/server` and `tests/unit/adapters/odoo`;
- `dists/domain-erp/pyproject.toml` and `dists/adapter-odoo/pyproject.toml`: entry point and hook `package`;
- both `e_agent_plugin.json`: `factory`;
- `pyproject.toml`: import-linter `root_packages` and contracts, with the core-never-imports-plugins contract now on `e_agent.plugins.*` and the "Plugins are guests" source modules now the packages under `e_agent.plugins.erp`;
- `tests/conformance/test_repo_layout.py`;
- the docs in Design refs, `README.md` and `AGENTS.md`;
- `.agents/skills/eng-foundations/references/rules.md`: ENG-ARCH-1 and ENG-ARCH-5 name the layout; check with `uv run python scripts/check_agent_skills.py`.

**Steps:**
- [ ] Write the failing tests:
  - `test_no_old_plugin_module_paths_remain`
  - the layout test asserting the new paths, `xfail(strict=True)` until the move
- [ ] Run `uv run python scripts/repo_move.py layout --set plugins`, then `uv run python scripts/repo_move.py check --docs`. Expected: no leftovers.
- [ ] Rebuild the wheels. Run `uv run python scripts/check_wheels.py` and compare the file lists through the prefix map. Expected: equal to before, minus the simulator files that moved out in 1d.5.
- [ ] Record the new pins for `domain-erp`, `odoo19` and `fixture-erp` with `scripts/plugin_inventory.py`, for the handoff and the owner's re-pin.
- [ ] Run the `full`, `pg` and `e2e` gates and `check_core_only.py`. Expected: pass; `export_openapi.py --check` shows no change.
- [ ] Commit `refactor: ERP plugins move under plugins/erp (ADR 0026)`.

---

## Part D: verification

### Task 1d.11: end-of-phase verification and bookkeeping

**Files:**
- `docs/handoffs/2026-10-13-phase1-structure.md`: a dated follow-up note (R-6) and the research-links ruling (R-5).
- `harness/state/1/harness-pilot-log.md`: HP-6 carried to H5 (R-8).
- `docs/plans/2026-10-14-phase2-execution-ir.md`: new paths; Task 2c.2 builds on the presets.
- `docs/plans/2026-10-12-odoo-tools-from-erp-bench.md`: new paths; the manifest `connection` item is dropped.
- `docs/roadmap.md`: Phase 1d status.
- `docs/design/principles.md`: PR-08 and PR-10 name their checks, status [I], and their backlog rows are removed.
- `docs/handoffs/<date>-phase1d-plugin-boundary.md`

**Steps:**
- [ ] Run `eng-verify` levels 1–3 on a clean tree and record each result.
- [ ] Run the phase review with `eng-review` against this plan. Fix findings as `1d.R<n>`.
- [ ] Write the handoff with `eng-handoff`. It records:
  - changes and each level's output;
  - rulings D1–D6;
  - changes outside the repository: the owner's re-pin and how to undo it;
  - what remains: the four infrastructure adapters become discoverable plugins in Phases 3 and 7 (DR-04).
- [ ] Commit `docs: Phase 1d handoff; Phase 2 and Odoo plans amended`.

### Task 1d.12: live check

- [ ] The owner re-pins the local live profile and runs the live check above through `live-sandbox`. The results go into the handoff, labelled live.
- [ ] Commit `docs: Phase 1d live check results`.

## Self-review

- **Spec coverage.**
  - Plugins folder and many ERP providers → D1, 1d.5, 1d.9 and 1d.10.
  - Enterprise beyond ERP and a reusable core → 1d.7 and 1d.8 (contract and core-only install), 1d.6 (no ERP default in the server), and the ADR 0026 filing rule.
  - R-1 → 1d.2. R-2 → 1d.4 and 1d.5. R-3 → 1d.3. R-4 → 1d.1, 1d.7 and 1d.10. R-5, R-6 and R-8 → 1d.11. R-7 → 1d.7.
  - DR-03 → 1d.2. DR-04 → 1d.5 and 1d.10.
  - ADR 0026 common-SDK amendment → 1d.2 (connection spec) and 1d.7b (HTTP helper, dependency closure).
  - Adoption review XA-02 → 1d.7 and 1d.10. XA-03 → 1d.7 (static check); its runtime probe → Phase 5.
  - Roadmap rule 1 → 1d.11 and 1d.12.
- **Placeholder scan.** No TBD. ADR 0026 settles `driver_factories`, `DriverFactory` and `DriverRequest`, and 1d.4 uses those names.
- **Name consistency.** The following are spelled the same in every task: `e_agent.plugins.erp.{domain,odoo,simulator}`, `fixture-erp`, `odoo19`, `domain-erp`, `adapter-erp-simulator`, `e-agent-erp`, `TaskPreset`, `task_presets`, `driver_factories`, `DriverFactory`, `DriverRequest`, `e_agent.sdk.connection`, `e_agent.sdk.http`, `e-agent-plugin-sdk[http]`, `fixture_profile_path`, `E_AGENT_PROFILE`, `check_core_only.py`, `STARTUP_REJECTED`, "Plugins are guests", `test_every_plugin_package_is_a_guest`, ADR 0026.
- **Review Focus coverage.** Items 1–12 each name a task and a test.
