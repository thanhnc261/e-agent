# Phase 1 task 1a.1: baseline evidence (2026-10-13)

## Summary

- **Plan:** [Phase 1 plan](../plans/2026-10-12-phase1-structure-refactor.md), Task 1a.1. Feature `F-1a-1` in `harness/state/1/features.json`.
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

## Wheel reference (the "must be identical after the move" list)

`unzip -l` of every wheel is in `evidence/baseline/unzip-l/` (local). The committed, backend-neutral reference is [2026-10-13-phase1-1a1-wheel-reference.txt](2026-10-13-phase1-1a1-wheel-reference.txt), 244 lines. For each of the 10 wheels it lists:
- the file entries, sorted;
- the distribution-identity fields of `METADATA` (`Name`, `Version`, `Requires-Python`, `Requires-Dist`, `Provides-Extra`), sorted;
- `entry_points.txt` without blank lines.

It is backend-neutral on purpose:
- Today's wheels are built by `uv_build` (`WHEEL` says `Generator: uv 0.11.25`, and every `pyproject.toml` has `build-backend = "uv_build"`).
- `uv_build` also writes zero-length directory entries such as `e_agent/` and `e_agent/kernel/`.
- The plan's `dists/<name>/pyproject.toml` uses hatchling, which writes file entries only and orders `METADATA` fields differently.
- So directory entries are dropped, the identity fields are sorted, and everything is sorted under `LC_ALL=C`. The output is the same under `C` and `en_US.UTF-8`.

Regenerate it after the move and diff (`<dir>` holds the 10 new wheels):

```sh
export LC_ALL=C
for w in $(ls <dir>/*.whl | sort); do
  di=$(unzip -Z1 "$w" | grep -m1 '\.dist-info/' | cut -d/ -f1)
  echo "## $(basename "$w")"
  echo "# files";        unzip -Z1 "$w" | grep -v '/$' | sort
  echo "# metadata";     unzip -p "$w" "$di/METADATA" | grep -E '^(Name|Version|Requires-Python|Requires-Dist|Provides-Extra):' | sort
  echo "# entry_points"; unzip -p "$w" "$di/entry_points.txt" 2>/dev/null | grep -v '^[[:space:]]*$'
done > new-reference.txt
diff docs/handoffs/2026-10-13-phase1-1a1-wheel-reference.txt new-reference.txt
```

Any line in the diff needs an explanation. A hatchling-only `.dist-info/` file (for example `licenses/`) is backend noise. Any change outside `.dist-info/` is a defect.

| Wheel (`-0.1.0-py3-none-any`) | Files | Outside `.dist-info/` | Entry points |
|---|---|---|---|
| `e_agent_adapter_agent_pydantic` | 5 | 2 | none |
| `e_agent_adapter_odoo` | 9 | 5 | `e_agent.plugins.v1: odoo19` |
| `e_agent_adapter_postgres` | 10 | 7 | none |
| `e_agent_adapter_secretstore_local` | 5 | 2 | none |
| `e_agent_adapter_shacl` | 5 | 2 | none |
| `e_agent_contracts` | 20 | 17 | none |
| `e_agent_domain_erp` | 43 | 39 | `e_agent.plugins.v1: domain-erp` |
| `e_agent_kernel` | 14 | 11 | none |
| `e_agent_plugin_sdk` | 11 | 8 | none |
| `e_agent_server` | 10 | 6 | `console_scripts: e-agent` |

No wheel contains `__pycache__` or `.pyc` entries. The domain-erp and odoo19 counts outside `.dist-info/` (39, 5) equal the plugin inventory's artifact file counts.

## Rulings

- The gate counts on `08eb020` are the baseline. Cost if wrong: 1a.3 compares against the wrong counts; re-run the gate on `ebfcf70` (about one minute).
- 1a.3 compares the wheel reference above plus `manifest_sha256` and `artifact_sha256`, not `wheel_sha256`. The build backend changes from `uv_build` to hatchling, so `WHEEL`, `RECORD` and the zip bytes change even when the payload is identical. Cost if wrong: a missed byte-level payload difference; `unzip -p` diffs of the payload files settle it.
- The reference drops directory entries and sorts the identity fields, so the backend switch does not cause false mismatches. Cost if wrong: a real difference hidden by the normalisation; the raw `unzip -l` lists in `evidence/baseline/unzip-l/` still show it.
- The inventory and listings use the wheels `check_wheels.py` built, not a second build. Cost if wrong: none for content; a rebuild from `08eb020` reproduces them.
- `make e2e` was run as an extra baseline although 1a.1 does not require it, because it touches no container. Cost if wrong: about two minutes.
- The Postgres gate was not run. This session's owner rule is "never touch any container", and the plan's Boundaries line allows containers only in 1c.11. Cost if wrong: a Postgres-only regression in 1a.3 (migration resources) has no pre-move reference; run it later on `08eb020`.

## Open items

- **Plan conflict for the owner.** The Global Constraints list "the Postgres run" in the gate after every task. The Boundaries line allows containers only in 1c.11. 1a.3 needs a ruling: either an `e-agent-test-*` Postgres container is allowed for the gate, or the Postgres run moves to 1c.11. In the second case the 10 skipped migration and recovery tests are not checked across the layout move until then.
- `new-task` lists `docs/handoffs/**` twice in `allowed_paths` when it is passed explicitly, because it is also implicit. The one-line dedupe belongs in `tools/harness/src/e_agent_harness/tasks.py`, which is outside this contract's allowed paths.
- `evidence/` is git-ignored, so the F-1a-1 evidence and the handoff refs validate only on this machine. In a fresh clone or worktree, `close-check` for 1a.1 reports them missing. The committed wheel reference and this summary carry the numbers 1a.3 needs.
