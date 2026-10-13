# Phase 1 task 1a.1: baseline evidence (2026-10-13)

## Summary

- **Plan:** [Phase 1 plan](../superpowers/plans/2026-10-12-phase1-structure-refactor.md), Task 1a.1. Feature `F-1a-1` in `harness/state/1/features.json`.
- **Branch:** `refactor/phase1-structure`, cut from `main` at `ebfcf70`. Not merged, not pushed.
- **Purpose:** the "must be identical after the move" reference for Task 1a.3. No product code changed; every commit on the branch touches only `harness/state/**` or `docs/handoffs/**`, so the product tree measured here is `main` at `ebfcf70`.
- **Raw outputs:** `evidence/baseline/` (git-ignored, local only). If it is lost, rebuild it from commit `08eb020` with the commands below.

## Gate counts

`uv run e-agent-harness gate full` on the clean tree at `08eb020`, evidence `evidence/gates/1a.1/2026-10-13T01-13-47+00-00.json`, all eight commands exit 0:

| Command | Result |
|---|---|
| `uv sync --locked` | 84 packages resolved, 80 checked |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 200 files already formatted |
| `uv run mypy` | no issues in 106 source files |
| `uv run lint-imports` | 117 files, 589 dependencies; 8 contracts kept, 0 broken |
| `uv run python scripts/export_openapi.py --check` | no change |
| `uv run pytest -q` | **572 passed, 30 skipped** |
| `pnpm --dir ui gen:check` | no diff |

The 30 skips (`pytest -rs`, `evidence/baseline/pytest-skips.txt`) are environmental: 20 "no sandbox Odoo" (`tests/integration/test_odoo_live*.py`), 8 "no isolated PostgreSQL test ledger" (`tests/integration/test_process_recovery.py`), 2 "E_AGENT_TEST_PG_DSN unset" (`packages/adapter-postgres/tests/test_migrations.py`).

`make e2e` (UI build plus Playwright conformance against a local fixture server, no containers): **150 passed, 4 skipped**, exit 0 (`evidence/baseline/make-e2e.txt`).

Not run: the Postgres gate (needs the ledger container; the plan allows containers only in 1c.11).

## `scripts/check_wheels.py`

`uv run python scripts/check_wheels.py` at `118dda8` (product tree identical to `08eb020`), exit 0:

```text
ok  e-agent-contracts: installs and imports from its own dependency closure
ok  e-agent-plugin-sdk: installs and imports from its own dependency closure
ok  e-agent-kernel: installs and imports from its own dependency closure
ok  e-agent-domain-erp: installs and imports from its own dependency closure
ok  e-agent-adapter-shacl: installs and imports from its own dependency closure
ok  e-agent-adapter-postgres: installs and imports from its own dependency closure
ok  e-agent-adapter-agent-pydantic: installs and imports from its own dependency closure
ok  e-agent-adapter-secretstore-local: installs and imports from its own dependency closure
ok  e-agent-adapter-odoo: installs and imports from its own dependency closure
ok  e-agent-server: installs and imports from its own dependency closure
ok  installed plugin bytes match trusted wheel inventories before activation
ok  installed e-agent demo completes outside the repository
ok  installed ERP-04..08 demos complete outside the repository
```

## Plugin inventory (fresh wheels)

The 10 wheels `check_wheels.py` built into `dist/` were copied to `evidence/baseline/wheels/`, and `uv run python scripts/plugin_inventory.py <wheel>` was run on them:

| Plugin | Wheel | `manifest_sha256` | `artifact_sha256` | Artifact files |
|---|---|---|---|---|
| `domain-erp` | `e_agent_domain_erp-0.1.0` | `2203e547f3a22979dc0eb826a3e8cd6a9a6e4e1012a2cc141178dc6ae2ec5679` | `0f1c8f61a8a3bcd3d1b1e7803c3df233ddead29be235a9bf2d769673a7a23c4e` | 39 |
| `odoo19` | `e_agent_adapter_odoo-0.1.0` | `4c2c34b5a38aebf2dbe800463c2cac4ad6a9d8c0e869cf9889dc47ce43feca81` | `8df983a76276dd2191569b3c45725929c072b1259b237e52fc2dada1b708c66f` | 5 |

Wheel `wheel_sha256` values (`evidence/baseline/wheels.sha256`) are recorded too, but they are not a comparator for 1a.3 (see rulings).

## Wheel file lists

`unzip -l` of every wheel is in `evidence/baseline/unzip-l/`; the sorted `unzip -Z1` name lists are in `evidence/baseline/names/`. The fingerprint is the first 16 hex digits of the sha256 of the sorted name list, so 1a.3 can compare without the local evidence:

| Wheel (`-0.1.0-py3-none-any`) | Entries | Outside `.dist-info/` | Name-list sha256 (16) |
|---|---|---|---|
| `e_agent_adapter_agent_pydantic` | 9 | 5 | `4e9c2e6b0fbf9885` |
| `e_agent_adapter_odoo` | 13 | 8 | `d407ea35bf740ec6` |
| `e_agent_adapter_postgres` | 15 | 11 | `0a92423d277b1179` |
| `e_agent_adapter_secretstore_local` | 9 | 5 | `27fc0067a62a3d6a` |
| `e_agent_adapter_shacl` | 9 | 5 | `9dee8e58bedfc15d` |
| `e_agent_contracts` | 24 | 20 | `a44a444213e3d305` |
| `e_agent_domain_erp` | 60 | 55 | `234cc76b34e2b929` |
| `e_agent_kernel` | 17 | 13 | `428faa10e4b07487` |
| `e_agent_plugin_sdk` | 14 | 10 | `db75fc8ec9d495a0` |
| `e_agent_server` | 14 | 9 | `a7a265717262e7bc` |

No wheel contains `__pycache__` or `.pyc` entries.

Reproduce a list after the move: `unzip -Z1 dist/<wheel>.whl | sort | shasum -a 256`.

## Rulings

- The gate counts on `08eb020` are the baseline. Cost if wrong: 1a.3 compares against the wrong counts; re-run the gate on `ebfcf70` (about one minute).
- 1a.3 compares sorted wheel name lists, `manifest_sha256` and `artifact_sha256`, not `wheel_sha256`. Wheel bytes include `RECORD` and zip metadata that can change when only the source location changes. Cost if wrong: a missed byte-level difference; a direct `unzip -p` diff of the wheels settles it.
- The inventory and listings use the wheels `check_wheels.py` built, not a second build. Cost if wrong: none for content; a rebuild from `08eb020` reproduces them.
- `make e2e` was run as an extra baseline although 1a.1 does not require it, because it touches no container. Cost if wrong: about two minutes.
- The Postgres gate was not run. Cost if wrong: a Postgres-only regression in 1a.3 has no pre-move reference; check out `08eb020` and run it then.

## Open items

- `new-task` lists `docs/handoffs/**` twice in `allowed_paths` when it is passed explicitly, because it is also implicit. This is a harness nit, out of scope for this task.
- Postgres baseline not recorded (see rulings).
