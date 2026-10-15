# Review: Phases 0 and 1, and the plugin boundary

Date: 2026-10-14 (review); recorded 2026-10-15 by Task 1d.1 of the [Phase 1d plan](../plans/2026-10-14-phase1d-plugin-boundary.md). Reviewer: `reviewer` subagent, fresh context. Scope: Phase 0 (cleanup) and Phase 1 (structure refactor) as merged to `main`, plus the owner's question whether ERP-specific folder names belong beside the core.

**Verdict:** rework. The rubric gives rework because R-1 to R-4 affect a contract. R-1 to R-3 are boundary debt that predates Phase 1: Phase 1's no-behaviour-change rule required moving that code verbatim. R-4 is about how the Phase 1 layout and its documents present the boundary. Phase 0 and Phase 1 otherwise did what their plan promised.

## Findings

| ID | Severity | Affects | Finding | Evidence (at review time) | Phase 1d task |
|---|---|---|---|---|---|
| R-1 | High | contract | The server hard-codes the provider id `odoo19` in `AUTH_PLACEMENT` and `LIVE_PROVIDERS_WITH_SANDBOX`. Both copy what the `odoo19` manifest already declares (the `connection` section's API-key placement, header and prefix, and `test_connection` `sandbox_info`), so one fact has two sources. Accepted ADR 0012 item 1 says adapter manifests declare the auth methods and `test_connection`. Predates Phase 1 | `src/e_agent/server/bootstrap.py:38-39, 207, 302`; `src/e_agent/adapters/odoo/e_agent_plugin.json`; ADR 0012 line 13; ENG-PLAN-2, ENG-ARCH-3 | 1d.2 |
| R-2 | Medium | contract | The composition root and the CLI import the ERP fixture package: `FakeErp`, `FIXTURE_BINDINGS`, `SCENARIOS`, `ScriptedErpDriver`, `DEFAULT_REFS`, `TASK_KINDS`; `Runtime.fake_erp` is typed `FakeErp`. The server cannot compose a second domain pack without code edits, and `erp/testing` ships in the production `domain-erp` wheel and its pin. HLD §4 lets the server depend on domains, so no gate rule is broken. Predates Phase 1 | `src/e_agent/server/bootstrap.py:21-25, 50, 226-242, 251-258`; `src/e_agent/server/cli.py:13-14, 114`; the `domain-erp` wheel lists `e_agent/erp/testing/*` (`docs/handoffs/2026-10-13-phase1-1a1-wheel-reference.txt:152-157`); ENG-ARCH-3 | 1d.4, 1d.5 |
| R-3 | Medium | contract | ERP task vocabulary sits in the generic profile schema and the CLI. `DriverConfig.task_kind` is a `Literal` of the eight ERP tasks; `demand_ref`, `product_ref` and `refs` are documented as ERP-04..08; `TASK_PROMPTS` holds the ERP demo prompts. A non-ERP profile is rejected by schema, and domain content lives in a CLI command, against AGENTS.md "Architecture rules". Predates Phase 1 | `src/e_agent/server/profile.py:53-67`; `src/e_agent/server/cli.py:23-37, 54-60, 231, 244`; ENG-ARCH-3 | 1d.3 |
| R-4 | Medium | contract | The layout and its documents do not show where the core ends and plugins begin. Only `e_agent.erp` (`domain-erp`) and `e_agent.adapters.odoo` (`odoo19`) are entry-point plugins with manifests; the other four adapters are wired by bootstrap. Yet `erp/` sits beside `contracts/`, `sdk/` and `kernel/`, the documents describe the tree only as grouped by layer, and the import contract "Core packages do not import agent frameworks" lists `e_agent.erp` as core. The owner's concern is valid | `dists/domain-erp/pyproject.toml` and `dists/adapter-odoo/pyproject.toml` are the only `e_agent.plugins.v1` entry points; `src/e_agent/server/bootstrap.py:15-18, 221`; `pyproject.toml` `[tool.importlinter]` last contract; target architecture §15; Phase 1 plan lines 12-25; ENG-PLAN-3 | 1d.1 (ADR 0026), 1d.7, 1d.10 |
| R-5 | Low | style | Four relative links in `research/` still point at pre-move design paths. Research is create-only (ENG-BOUND-2), so they stay broken, and the handoff's open item "allow a link-only rewrite of research/" is moot | `uv run python scripts/repo_move.py check`: `research/14-enterprise-wide-agent-experience.md` (3 links), `research/mockups/agentic-chat-v4/design-system/README.md` (1 link); ENG-DOC-1 | 1d.11 (ruling D5) |
| R-6 | Low | style | The Phase 1 handoff still says "Not merged, not pushed", while roadmap row 1 says merged to `main`. It is a dated record with no follow-up note | `docs/handoffs/2026-10-13-phase1-structure.md:6`; roadmap Phase 1 row | 1d.11 |
| R-7 | Low | style | A kernel docstring cites ERP task ids. Comment only: no ERP, Odoo or procurement identifiers appear in contracts, SDK or kernel code | `src/e_agent/kernel/proposals.py:230` | 1d.7 |
| R-8 | Low | style | Of the Phase 1 harness pilot findings, HP-6 (a contract has one gate set while the plan needs `full`, `pg` and `e2e`) is still open. HP-13 (the `pg` gate pointing at the live ledger) is resolved by `[gate_guards.pg]` | `harness/state/1/harness-pilot-log.md:35, 42`; `harness/context.toml:64-70` | 1d.11 (carried to H5) |

## What the reviewer checked, and what held

- `uv run lint-imports`: 9 contracts kept, 0 broken.
- `uv run pytest -q tests/conformance`: 185 passed, including the namespace layout (no `src/e_agent/__init__.py`, no `packages/` or `apps/`).
- `scripts/repo_move.py check` and `check --docs`: 0 broken links and 0 old-path references in code, configuration and current documents; the 4 broken links are in `research/`.
- The largest kernel module, `memory_store.py`, has 455 lines, under the 500 limit.
- `dists/` holds 10 build configurations.
- The `domain-erp` wheel file list matches the 1a.1 reference.
- The Phase 0 `/evidence/` ignore rule is anchored to the root.
- HP-13 is fixed.

## What the reviewer did not run

The full gate, the full pytest suite, the Postgres run, `make e2e`, `check_wheels.py` and the wheel rebuild, the OpenAPI check, the UI tests, the per-method byte-identity and R100 rename claims, and the contents of the Phase 0 archive. None of these results is claimed here.

## The owner's concern: ERP-specific folder names

Only two packages are plugins in the discovery sense (an `e_agent.plugins.v1` entry point and an `e_agent_plugin.json` manifest): `src/e_agent/erp/` (`domain-erp`) and `src/e_agent/adapters/odoo/` (`odoo19`). The other four adapters (postgres, shacl, pydantic_ai, secretstore_local) are port implementations that bootstrap wires in directly. The core packages (contracts, SDK, kernel) contain no ERP code or imports; the ERP leakage is in `server/` (R-1 to R-3). [ADR 0026](../adr/0026-plugin-layout-and-reusable-core.md) decides the layout that makes the boundary visible.
