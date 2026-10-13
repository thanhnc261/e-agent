# Phase 1: Structure Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** give the repository a clear structure before the execution-IR work. Phase 1 has three parts:
- **1a (code layout):** all Python code moves into one layer-grouped tree, `src/e_agent/...`, with no repeated folder names. Packages remain independently releasable.
- **1b (docs, AGENTS.md, CLAUDE.md):** documents move to obvious places, and the agent instructions are rewritten for the new layout and the roadmap rules.
- **1c (kernel split):** the 1,827-line `coordinator.py` and the 764-line `api.py` are split into focused modules. Behaviour does not change.

**Architecture (owner decision 2026-10-12: group by layer and avoid duplicated names such as `apps/server/src/e_agent/server`):**

```text
e-agent/
├── src/e_agent/                      all Python code, one tree, grouped by layer
│   ├── contracts/  sdk/  kernel/     core (portable records, ports, trust anchor)
│   ├── erp/                          domain pack(s)
│   ├── adapters/                     pydantic_ai/ postgres/ odoo/ shacl/ secretstore_local/
│   └── server/                       app: composition root, API, CLI
├── dists/<distribution>/pyproject.toml   one build/release config per distribution (10)
├── tests/
│   ├── unit/<part>/                  contracts/ sdk/ kernel/ erp/ adapters/<name>/ server/
│   ├── conformance/  integration/  replays/
├── addons/e_agent_bridge/   ui/   profiles/   scripts/   evals/
├── docs/   research/   archive/
└── .agents/skills/  .claude/
```

**Why this keeps the architecture rules:**
- Every distribution still has its own `dists/<name>/pyproject.toml`, with its own dependencies, entry points and wheel. Hatchling builds the wheel from `force-include` of its sub-tree.
- In development each distribution is installed editable, with `dev-mode-dirs = ["../../src"]`, so plugin discovery still sees separate distributions with their own entry points and manifests.
- Import-linter enforces the layer boundaries on the shared tree.

**Spike evidence (2026-10-12, scratchpad):** with uv and hatchling, two distributions from one shared `src/e_agent/` tree
- built separate wheels containing only their own sub-package;
- installed editable side by side;
- imported across each other;
- kept separate `importlib.metadata` distributions with their own entry points.

**Tech stack:** uv workspace, hatchling (`force-include`, `dev-mode-dirs`), import-linter, mypy, ruff, pytest, plus a Python mover script that rewrites paths and links.

**Spec:**
- [Roadmap](../roadmap.md) Phase 1
- [Target architecture](../design/target-architecture.md) §15 (repository structure; this plan supersedes its `packages/<dist>/src/...` shape, and §15 is updated in Task 1b.4), §16 (module map), §3.3 (kernel components after the SR-06 split)
- Roadmap P1 exit: "line-count and import contracts per kernel module"

## Global Constraints

- **No behaviour change.**
  - Every existing test passes unchanged except for import or path lines.
  - Public import names stay the same, for example `e_agent.kernel.coordinator.RunCoordinator`.
  - The OpenAPI document does not change (`export_openapi.py --check`).
- **Code moves verbatim, by `git mv`, so history is preserved.** File contents change only where a path is embedded:
  - pyproject configs
  - scripts that locate packages
  - docs links
- **Distribution identity is unchanged.** The same 10 distribution names, versions, dependencies and entry points are kept. Each distribution's wheel contains exactly the files it contained before; check this with `scripts/check_wheels.py`.
- **AGENTS.md rule change.** "Python code lives in `packages/<dist>/src/e_agent/<part>/`" becomes "Python code lives in `src/e_agent/<part>/`; each distribution's build config is in `dists/<dist>/`; never add `src/e_agent/__init__.py`". This is updated in Task 1b.3.
- **Gate after every task:**
  - `uv sync --locked`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run mypy`
  - `uv run lint-imports`
  - `uv run python scripts/export_openapi.py --check`
  - `uv run pytest -q`
  - `(cd ui && pnpm gen:check)`
  - The Postgres run, plus `make e2e` after the layout move.
- **Commits.** Use branch `refactor/phase1-structure`. Stage with explicit `git add` paths. Every commit carries the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Boundaries.** No container is touched except during the live check in 1c.11 (`odoo19-learning` and `e-agent-ledger` only).

## Review Focus

1. **Plugin artifact pins.** `artifact_sha256` is computed over the files of the plugin's package root. A moved file must keep the same set of files inside each wheel. Compare `scripts/plugin_inventory.py` output before and after the move: the `manifest_sha256` must be equal, and `artifact_sha256` must be equal if the wheel contents are identical.
2. **Resource files.** Manifests, ontology, shapes, rule inventories and migrations are package data. `force-include` of the whole sub-tree must carry them, and `importlib.resources` lookups must still resolve. The existing packaging tests and `check_wheels.py` cover this.
3. **Tests importing siblings through relative imports** (`from .conftest import …`). Keep each test folder a package (`__init__.py`). Avoid duplicate test module basenames across folders, or keep the `__init__.py` files so pytest's rootdir-based import names stay unique.
4. **Mixin shadowing in the kernel split.** A fitness test asserts that every method is defined exactly once across the `RunCoordinator` MRO.
5. **Plans written by skills to `docs/superpowers/plans`.** CLAUDE.md overrides this to `docs/plans/`.

---

## Part 1a: code layout (one layer-grouped tree)

### Task 1a.1: Baseline evidence

- [x] **Step 1:** Record the baseline:
  - the gate counts;
  - `uv run python scripts/check_wheels.py` output;
  - `scripts/plugin_inventory.py` hashes for `domain-erp` and `odoo19`, built from fresh wheels.

  Save all of it to the task report.
- [x] **Step 2:** For every wheel, list its files with `unzip -l` on all 10 built wheels. This list is the "must be identical after the move" reference.

### Task 1a.2: Mover script

**Files:** create `scripts/repo_move.py`, with these subcommands:
- `layout`: performs the code move below with `git mv` and generates each `dists/<name>/pyproject.toml` from the old `<pkg>/pyproject.toml` (same `[project]` table, entry points and dependencies; hatch `force-include` and `dev-mode-dirs` added).
- `links`: rewrites Markdown links. This is the Phase 0 mover, generalised.
- `check`: reports broken relative links outside `archive/`, and any remaining reference to an old path in tracked text files.

**Test:** create `tests/conformance/test_repo_layout.py`. It asserts:
- no `packages/` or `apps/` directory remains;
- every `dists/*/pyproject.toml` has `force-include` entries that exist;
- `src/e_agent/__init__.py` does not exist.

**Code move map** (`git mv`; tests move to `tests/unit/<part>/`):

| From | To (code) | To (tests) | Distribution config |
|---|---|---|---|
| `packages/contracts/src/e_agent/contracts` | `src/e_agent/contracts` | `tests/unit/contracts` | `dists/contracts` |
| `packages/plugin-sdk/src/e_agent/sdk` | `src/e_agent/sdk` | `tests/unit/sdk` | `dists/plugin-sdk` |
| `packages/kernel/src/e_agent/kernel` | `src/e_agent/kernel` | `tests/unit/kernel` | `dists/kernel` |
| `packages/domain-erp/src/e_agent/erp` | `src/e_agent/erp` | `tests/unit/erp` | `dists/domain-erp` |
| `packages/adapter-agent-pydantic/src/e_agent/adapters/pydantic_ai` | `src/e_agent/adapters/pydantic_ai` | `tests/unit/adapters/pydantic_ai` | `dists/adapter-agent-pydantic` |
| `packages/adapter-postgres/src/e_agent/adapters/postgres` | `src/e_agent/adapters/postgres` | `tests/unit/adapters/postgres` | `dists/adapter-postgres` |
| `packages/adapter-odoo/src/e_agent/adapters/odoo` | `src/e_agent/adapters/odoo` | `tests/unit/adapters/odoo` | `dists/adapter-odoo` |
| `packages/adapter-shacl/src/e_agent/adapters/shacl` | `src/e_agent/adapters/shacl` | `tests/unit/adapters/shacl` | `dists/adapter-shacl` |
| `packages/adapter-secretstore-local/src/e_agent/adapters/secretstore_local` | `src/e_agent/adapters/secretstore_local` | `tests/unit/adapters/secretstore_local` | `dists/adapter-secretstore-local` |
| `apps/server/src/e_agent/server` | `src/e_agent/server` | `tests/unit/server` | `dists/server` |

`src/e_agent/` and `src/e_agent/adapters/` get **no** `__init__.py`; they stay namespace packages.

Generated `dists/kernel/pyproject.toml` (shape; values come from the old file):

```toml
[project]
name = "e-agent-kernel"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["e-agent-contracts>=0.1,<0.2", "e-agent-plugin-sdk>=0.1,<0.2"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
dev-mode-dirs = ["../../src"]

[tool.hatch.build.targets.wheel.force-include]
"../../src/e_agent/kernel" = "e_agent/kernel"
```

Steps:
- [x] **Step 1:** Write the conformance test. It fails, because `packages/` still exists.
- [x] **Step 2:** Implement `repo_move.py layout`. It runs in Task 1a.3.

**Execution notes (2026-10-13, task 1a.2 review):**
- **The move runs in 1a.3.** A tree that is moved but has old tooling cannot pass the per-task gate. 1a.2 commits the mover and its tests; `test_repo_layout.py` is `xfail(strict=True)` until the move.
- **No static `force-include`.** hatchling also copies a static `force-include` into the editable install. The copy in site-packages then shadows `src/`, and edits become invisible. Instead, each `dists/<name>/pyproject.toml` names its package in a shared build hook, `dists/_hooks/src_tree.py`. The hook adds the sub-tree to standard wheels only. `test_repo_layout.py` asserts that every package imports from `src/`. The root workspace excludes `dists/_hooks`.
- **Wheels only (task 1a.3 review).** The hook runs for every target. It refuses an sdist with a clear message, because an sdist cannot carry the shared `src/` tree; otherwise it would build an archive with no code. Build with `uv build --package <name> --wheel`, as `check_wheels.py` and CI already do.
- **`uv_build` cannot be kept.** It refuses a `module-root` outside the project directory.
- **ruff isort classification.** `[tool.ruff] src = ["."]` keeps `e_agent` classified as before the move, so moved files stay byte-identical. Otherwise ruff re-sorts the imports in 48 files.
- **`research/` is read-only.** `links` never rewrites it; `check` reports its broken links separately and does not fail on them.
- **`check` categories.** `check` fails on broken links and on old paths in code and config. `check --docs` also fails on old paths named in current Markdown; dated records (`docs/adr`, `handoffs`, `plans`, `reviews`, `specs`, `superpowers`) are exempt.

### Task 1a.3: Tooling and path references

- [x] Update the root `pyproject.toml`:
  - `[tool.uv.workspace] members = ["dists/*"]`;
  - the mypy `mypy_path` / `files` point to `src` and `tests`;
  - `[tool.pytest.ini_options] testpaths = ["tests"]`;
  - the import-linter `root_packages` are unchanged (`e_agent`), and the existing contracts are kept;
  - ruff `src` paths.
- [x] Update the remaining path references:
  - `.github/workflows/ci.yml` (`pytest -q packages/kernel` becomes `tests/unit/kernel`);
  - `.github/workflows/odoo-live.yml` (wheel builds use `--package`, so they are unchanged; verify);
  - `scripts/qualify_model.py:75` (package roots);
  - `scripts/check_wheels.py`;
  - `scripts/plugin_inventory.py`;
  - the `Makefile`.
- [x] Run `uv lock` (the lock file changes only in source paths).
- [x] Run the full gate and `make e2e`, then `check_wheels.py`. **Wheel file lists are identical** to Task 1a.1; the plugin inventory `manifest_sha256` values are identical.
- [x] Commit: `refactor(repo): one layer-grouped src/e_agent tree; per-distribution configs in dists/ (no behaviour change)`.

### Task 1a.4: Editor hygiene

- [x] Add `.vscode/settings.json` with `files.exclude` and `search.exclude` for `**/__pycache__`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.import_linter_cache`, `ui/**/node_modules` and `ui/**/dist`. It is committed as a project setting.
- [x] Commit: `chore(editor): hide caches in the workspace`.

---

## Part 1b: docs structure, AGENTS.md, CLAUDE.md

### Task 1b.1: Designs into `docs/design/`

- [x] Run `scripts/repo_move.py links --move docs/high-level-design.md docs/mvp-detailed-design.md docs/target-architecture.md docs/ui-architecture.md docs/frontend-development-guide.md docs/integration-management.md docs/integration-auth-sdk.md docs/threat-model.md docs/implementation-plan.md --to docs/design`.
- [x] `check` must report 0 broken links. Commit.

### Task 1b.2: Plans and specs out of `docs/superpowers/`

- [x] Move the active plans (core, odoo-tools, dev-harness, phase1) into `docs/plans/`, and `docs/superpowers/specs/*` into `docs/specs/`.
- [x] Remove `docs/superpowers/`.
- [x] Update the plan-location sentence in the `docs/roadmap.md` Rules.
- [x] `check` must report 0 broken links. Commit.

### Task 1b.3: AGENTS.md, CLAUDE.md and README

- [x] **AGENTS.md**:
  - **Current state**: say that work is ordered by `docs/roadmap.md` and that `archive/` is history.
  - **Read before changing**: list `docs/roadmap.md`, `docs/design/*`, the ADR index, and the current phase plan.
  - **New section "How work is done"**: the roadmap's five rules (detailed plan first, design first, toggles with fallback, trust anchor unchanged, environment boundaries), plus per-task review and end-to-end verification.
  - **New section "Repository map"**: one line per top-level folder of the new tree.
  - **Development rule for the new layout**: `src/e_agent/<part>/`, `dists/<dist>/`, and no `src/e_agent/__init__.py`.
  - **Environment boundaries**: only `odoo19-learning` and e-agent's own containers; never `odoo-bench` or the lab experiments.
- [x] **CLAUDE.md** stays short and Claude-specific:
  - Plans go to `docs/plans/`, overriding the superpowers default.
  - Use subagent-driven execution with the git-ignored ledger `.superpowers/sdd/`.
  - Use the `ag-*` skills for UI.
  - Use the advisor for decisions.
  - Follow the commit trailer policy.
  - Point to AGENTS.md for everything shared.
- [x] **README**:
  - The status points to `docs/roadmap.md`.
  - The commands use the new paths.
  - The "Live agent" section is unchanged except for the paths.
  - Do not claim live qualification.
- [x] Run `check` (0 broken links) and `scripts/check_agent_skills.py`, then the gate. Commit.

### Task 1b.4: Design §15 update

- [x] Replace the `packages/...`/`apps/...` tree in `docs/design/target-architecture.md` §15 with the new layout. Mark it `[I]` and add a one-line rationale with this plan's link. Update the §16 "Location today" paths.
- [x] Commit.

---

## Part 1c: kernel and server split (behaviour-preserving)

### Task 1c.1: Pin the public surface

**Files:** create `tests/unit/kernel/test_structure.py`.

- [x] Inventory every name imported from `e_agent.kernel.coordinator` by tests, scripts and the server (`git grep -n "from e_agent.kernel.coordinator import\|coordinator\._"`). Assert that each name is still importable.
- [x] Assert that these public methods exist: `start_run`, `admit_run`, `start_admitted_run`, `set_text_sink`, `release_continuation`, `get_run`, `accept_input`, `continue_input`, `resume_input`, `pending_approval`, `sweep_expired_approvals`, `expire_approval`, `decide`, `reconcile`, `cancel`, `recover`, `recover_run`.
- [x] The test passes on the unsplit code. Commit.

### Tasks 1c.2–1c.8: one module per task, moved verbatim into `src/e_agent/kernel/`

Each task does the following:
- Create `class <Name>Mixin:` with the methods listed below, unchanged.
- Remove those methods from `coordinator.py` and add the mixin to the `RunCoordinator` bases.
- Run `pytest -q tests/unit/kernel`, then the gate.
- Commit `refactor(kernel): move <area> into <module>.py (no behaviour change)`.

| Task | Module | Moves |
|---|---|---|
| 1c.2 | `continuation.py` | `_Continuation`, `_GatewayReader`, `_read_cont`, `_peek_cont`, `_load_cont`, `_snapshot`, `_persist`, `_timed` (private names re-exported from `coordinator.py`) |
| 1c.3 | `transitions.py` | `_check_run_transition`, `_set_run_state`, `_transition` |
| 1c.4 | `run_loop.py` | `_drive`, `accept_input`, `continue_input`, `resume_input`, `_exhausted` |
| 1c.5 | `gateway.py` | `_gateway_read`, `_record_rejected_read` |
| 1c.6 | `proposals.py` | `_handle_proposal`, `_handle_answer`, `_validate` |
| 1c.7 | `approval_flow.py` (`approval.py` keeps digests) | `pending_approval`, `_expire_pending`, `_enqueue_expiry`, `sweep_expired_approvals`, `expire_approval`, `decide` |
| 1c.8 | `dispatch.py`, `verification.py`, `recovery.py` | `_dispatch`, `_staleness`, `_apply_receipt` / `_verify`, `_finish_verified` / `reconcile`, `cancel`, `recover`, `recover_run`, `_recover_run` |

`coordinator.py` keeps `__init__`, `_prepare_run`, `start_run`, `admit_run`, `start_admitted_run`, `set_text_sink`, `release_continuation`, `get_run` and the constants. It ends at about 200 lines.

The mixins must type-check against the attributes `__init__` sets. Declare those attributes once as class-level annotations in a shared base (`continuation.py`), so mypy sees `self._store` and the rest everywhere with no `type: ignore`.

**Execution notes (2026-10-13, task 1c.1):**
- **`ContinuationMixin` is the base.** It holds the attribute annotations and the continuation methods. Every later mixin subclasses it, so `_persist`, `_snapshot` and `_load_cont` are visible everywhere.
- **Cross-mixin calls.** The mixins call each other in cycles (`_drive` and `_handle_proposal`; `_dispatch` and `_drive`), so no linear inheritance chain type-checks. The base declares a stub for each method that one mixin calls on another, under `if TYPE_CHECKING:`. The stub copies the signature, and its body is `raise NotImplementedError`. At runtime the stubs do not exist, so the "defined exactly once" fitness test still holds. mypy decides which stubs exist: only the methods it reports as missing get one.
- **Constants move with their users.** `CONTINUATION_SCHEMA` and `LOG` move to `continuation.py`; `LOG` keeps the logger name `e_agent.kernel.coordinator`. `coordinator.py` re-exports them with `DEFAULT_APPROVAL_TTL`, `_Continuation` and `_GatewayReader`, and `test_structure.py` pins all of them.
- **One annotation changes.** `_GatewayReader.__init__` annotated its argument as `RunCoordinator`. It now names the base class: importing `coordinator` from `continuation.py`, even under `TYPE_CHECKING`, would break the 1c.9 import contract.
- **Two annotations are dropped.** If mypy reports the `__init__` annotations of `_runs` and `_active_calls` as redefinitions, they are removed there, because the base declares those attributes.
- **Verbatim evidence.** Each move slices method text by `ast` line ranges. A comparison script checks every moved method byte for byte against the parent commit and prints the result.

### Task 1c.9: Fitness tests and import contracts

- [x] `test_each_method_defined_once` checks across the `RunCoordinator` MRO.
- [x] `test_kernel_module_size` checks that every file in `src/e_agent/kernel/*.py` has at most 500 lines.
- [x] Add an import-linter contract: no kernel module except `coordinator` imports `e_agent.kernel.coordinator`. The existing layer contracts stay.
- [x] Run the gate, then commit.

### Task 1c.10: Server `worker.py` and `streaming.py`

- [x] Move `ApiState.worker`, `_run_work`, `sweeper` and `_mark_failed` into `src/e_agent/server/worker.py`. Move `PublicTextBus` and the SSE helpers into `src/e_agent/server/streaming.py`. Keep the code unchanged, and re-export from `api.py` any name the tests import.
- [x] Run the gate, `make e2e`, and `export_openapi.py --check` (it must report no change). Then commit.

### Task 1c.11: Live check, design and roadmap

- [x] Restart the live stack. Rebuild the wheels and confirm the plugin pins match Task 1a.1; if any wheel content changed, re-pin and explain why. Run the four live flows from the real-agent handoff; the results must match.
- [x] In target-architecture §15 and §16, mark the kernel and server modules `[I]` ("mixins behind the facade (Phase 1); collaborators later if needed").
- [x] Mark roadmap Phase 1 as Done. Commit.

## Self-review

- **Spec coverage.** Owner layout decision → 1a. Docs, AGENTS.md and CLAUDE.md → 1b. SR-06 split and the P1 line-count and import contracts → 1c. Design §15 and §16 → 1b.4 and 1c.11.
- **Placeholders.** The move map and method lists are complete (`coordinator.py` sections at lines 146–1747, `42d603f`).
- **Out of scope.** Feature-toggle infrastructure (the first task of Phase 2), any behaviour change, and the C4 worker *process* role.
