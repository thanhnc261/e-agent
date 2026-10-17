# Engineering rules

Each rule has one ID, a one-sentence statement, its source, how it is enforced (`gate`, `test`, `review`, `hook`, `permission`, `command`) and the evidence that shows it holds. IDs are stable; retired rules keep their number with the statement "Retired".

## Architecture

### ENG-ARCH-1 — Layer direction

- **Statement:** Dependencies point one way: contracts ← sdk ← kernel and domains ← adapters ← server; the kernel never imports domains, adapters or server; the core (`contracts`, `sdk`, `kernel`, `server`) never imports a plugin under `e_agent.plugins.*` (the ERP plugins are `e_agent.plugins.erp.{domain,odoo,simulator}`); and adapters never import kernel internals or sibling adapters.
- **Source:** AGENTS.md "Architecture rules"; ADR 0026; `[tool.importlinter]` contracts in `pyproject.toml` (among them "Core never imports plugins").
- **Enforcement:** gate
- **Evidence:** `uv run lint-imports` reports every contract kept.

### ENG-ARCH-2 — Portable contracts

- **Statement:** Contract types hold portable records only; vendor, framework and ORM objects never cross a contract boundary, and domain-specific fields live in domain APIs.
- **Source:** AGENTS.md "Architecture rules".
- **Enforcement:** review
- **Evidence:** the diff adds no framework or vendor type to `e_agent.contracts`.

### ENG-ARCH-3 — Composition at bootstrap

- **Statement:** Bootstrap chooses concrete implementations; domain logic does not live in HTTP handlers, CLI commands or prompts.
- **Source:** AGENTS.md "Architecture rules".
- **Enforcement:** review
- **Evidence:** handlers and commands delegate to kernel or domain code; the review names the delegation.

### ENG-ARCH-4 — No speculative structure

- **Statement:** No unused abstractions or empty future packages; an extension seam exists only for a concrete use case or an explicit trust boundary.
- **Source:** AGENTS.md "Architecture rules".
- **Enforcement:** review
- **Evidence:** every new module has a caller or a test in the same change.

### ENG-ARCH-5 — Namespace package layout

- **Statement:** Product code lives in `src/e_agent/<part>/` with one build config per distribution in `dists/<dist>/` after roadmap Phase 1a; plugins live in `src/e_agent/plugins/<area>/<name>/` (ADR 0026); and no `__init__.py` is ever added to `src/e_agent/`, `src/e_agent/adapters/`, `src/e_agent/plugins/` or `src/e_agent/plugins/erp/`.
- **Source:** AGENTS.md "Development and verification"; Phase 1 plan Global Constraints.
- **Enforcement:** test
- **Evidence:** `tests/conformance/test_repo_layout.py` passes.

## Trust anchor

### ENG-TRUST-1 — Model output is a proposal

- **Statement:** Model output cannot grant approval, change policy or budgets, install plugins, publish ontology or mark its own task verified.
- **Source:** AGENTS.md "Execution and data integrity"; roadmap rule 4.
- **Enforcement:** review, test
- **Evidence:** a test shows a model proposal cannot move a run to approved or verified.

### ENG-TRUST-2 — Kernel owns the state machines

- **Statement:** The run and action state machines, the action gateway, approval digests, admission and verification stay in the kernel, and every tool call including reads passes through host authorization and the gateway.
- **Source:** roadmap rule 4; AGENTS.md "Execution and data integrity".
- **Enforcement:** review, gate
- **Evidence:** no transition table, digest or admission code outside `e_agent.kernel`; import contracts kept.

### ENG-TRUST-3 — Approval binds the exact action

- **Statement:** Approval binds the normalised action, its scope and versions; changed facts or policy are revalidated and stale approval is rejected.
- **Source:** AGENTS.md "Execution and data integrity"; ADR 0006; ADR 0014.
- **Enforcement:** test
- **Evidence:** approval digest and freshness tests pass for the changed behaviour.

### ENG-TRUST-4 — Evidence before writes, atomic local state

- **Statement:** Admission and dispatch evidence is persisted before any write, local state and event updates are atomic, and no database transaction spans a model or ERP call.
- **Source:** AGENTS.md "Execution and data integrity"; ADR 0003.
- **Enforcement:** review, test
- **Evidence:** the write path records admission before dispatch; store conformance tests pass.

### ENG-TRUST-5 — Unknown outcomes stay unknown

- **Statement:** An external timeout can mean UNKNOWN; a possibly committed write is never replayed blindly, exactly-once is never claimed without provider guarantees, and outcomes are verified by independent read-back that distinguishes committed effect from business success.
- **Source:** AGENTS.md "Execution and data integrity"; ADR 0014; ADR 0018.
- **Enforcement:** test
- **Evidence:** reconciliation and verification tests cover the changed write path.

## Toggles and fallback

### ENG-TOGGLE-1 — Every runtime feature has a toggle

- **Statement:** Every new runtime feature ships behind a profile toggle with modes `off`, `shadow` and `on`, where `shadow` computes and records the new path but acts on the existing one.
- **Source:** roadmap rule 3.
- **Enforcement:** review, test
- **Evidence:** the profile schema has the toggle and a test exercises each mode.

### ENG-TOGGLE-2 — Fallback only before a reservation

- **Statement:** With the toggle `on`, a failure before any write is reserved falls back to the existing path and records `feature.fallback` with a reason code; after a reservation there is no fallback and the run fails closed or goes to reconciliation.
- **Source:** roadmap rule 3.
- **Enforcement:** test
- **Evidence:** tests for the pre-reservation fallback and the post-reservation fail-closed path.

### ENG-TOGGLE-3 — Toggles are observable

- **Statement:** `/health/ready` reports the active toggles and the evidence bundle records them.
- **Source:** roadmap rule 3.
- **Enforcement:** test
- **Evidence:** readiness and evidence-bundle tests include the toggle.

## Stores

### ENG-STORE-1 — Both stores

- **Statement:** Behaviour that touches the run store passes the store conformance suite on the memory store and on PostgreSQL before the phase closes.
- **Source:** target architecture, Stores row (store conformance); roadmap rule 1 (the Postgres run).
- **Enforcement:** test, gate
- **Evidence:** the deterministic suite and the Postgres run (`E_AGENT_TEST_STORE=postgres`) both pass.

## Evidence

### ENG-EVID-1 — Evidence is tied to a clean commit

- **Statement:** Gate evidence is recorded after the commit on a clean tree, and a task closes only when `close-check` accepts that evidence.
- **Source:** harness plan, principle P6 and the H2 close ritual.
- **Enforcement:** command
- **Evidence:** `uv run e-agent-harness close-check` prints `ok: task may close`.

### ENG-EVID-2 — Honest reporting

- **Statement:** Deterministic fixture results and live model or ERP results are reported separately, and every failure, skipped check and environmental blocker is named.
- **Source:** AGENTS.md "Development and verification".
- **Enforcement:** review
- **Evidence:** the handoff lists each verification level with its result or its blocker.

### ENG-EVID-3 — No secrets in evidence

- **Statement:** Evidence, handoffs, logs and traces contain no credentials; outputs are redacted before they are written and only authorized, redacted evidence is exported.
- **Source:** AGENTS.md "Development and verification".
- **Enforcement:** command, review
- **Evidence:** evidence files contain `[REDACTED]` where a secret appeared; the review greps for key material.

### ENG-EVID-4 — Gates fail on empty input

- **Statement:** A gate, report or scan prints how many cases it ran and fails when that number is zero; a vacuous pass is a defect. A new gate gets a test that feeds it empty input.
- **Source:** AGENTS.md "Development and verification"; PR-31; adoption review XA-04.
- **Enforcement:** test, review
- **Evidence:** `test_release_report_fails_on_zero_cases` (`tests/conformance/test_release_report.py`) passes.

**Known silent-pass paths** (finite; add an entry only with the task that fixes it):

- `scripts/release_report.py`: passed 0/0; fixed in Hygiene H.1.
- The replay `TASKS` constant in `tests/unit/server/test_recorded_model_replays.py`: an empty list passes; open, fixed in Hygiene H.4.

## Boundaries

### ENG-BOUND-1 — Sandbox only

- **Statement:** Only the `odoo19-learning` sandbox and containers e-agent creates are touched; `odoo-bench` and the lab experiments never are, and live business data is never read or reset.
- **Source:** roadmap rule 5; harness manifest `[environment]`; AGENTS.md "Development and verification".
- **Enforcement:** permission, hook
- **Evidence:** permission deny rules for `odoo-bench`; the manifest's allowed and denied container patterns.

### ENG-BOUND-2 — Protected paths

- **Statement:** `archive/**` is read-only, `research/**` accepts new files only (existing reports stay as written; owner decision 2026-10-13), and a change under `addons/**` bumps the bridge version in the same change.
- **Source:** harness manifest `[protected]` (`read_only`, `create_only`); AGENTS.md "Documentation and completion" (preserve research reports).
- **Enforcement:** hook, command
- **Evidence:** `uv run e-agent-harness check-scope` passes on the change.

### ENG-BOUND-3 — No credentials anywhere in the repository

- **Statement:** Credentials never appear in commits, logs, prompts, traces or documentation; keys live outside the repository and secret profiles are `*.local.json`.
- **Source:** AGENTS.md "Development and verification"; README "Live agent" section.
- **Enforcement:** review
- **Evidence:** the diff and the handoff contain no key material; local profiles are ignored by git.

## Planning and design

### ENG-PLAN-1 — Detailed plan first

- **Statement:** A phase starts only after its bite-sized plan is written in `docs/plans/`, linked from the roadmap and reviewed by the owner.
- **Source:** roadmap rule 1.
- **Enforcement:** command
- **Evidence:** `uv run e-agent-harness validate-context` finds the active plan with its required sections.

### ENG-PLAN-2 — Contract changes need an ADR

- **Statement:** A change to a contract or a boundary needs an ADR, and a Proposed ADR changes nothing until the owner accepts it.
- **Source:** roadmap rule 2; `docs/adr/README.md` status rules.
- **Enforcement:** review
- **Evidence:** the ADR exists with status Accepted before the phase merges.

### ENG-PLAN-3 — Code and design never drift silently

- **Statement:** When code and design disagree, one of them is fixed explicitly in the same change, and a plan that implementation diverged from is updated in the same commit.
- **Source:** roadmap rule 2; harness plan principle P3.
- **Enforcement:** review
- **Evidence:** the commit that diverges also edits the plan or the design, and the handoff records the ruling.

## Working method

### ENG-WORK-1 — One task, inside its contract

- **Statement:** A session works on one task contract per context window, and every edit stays inside the contract's allowed paths.
- **Source:** harness plan principle P2 and the session loop.
- **Enforcement:** hook, command
- **Evidence:** `check-scope` passes; the progress log shows one task per session.

### ENG-WORK-2 — Test first, verbatim moves

- **Statement:** A failing test is watched before production code is written, and a refactor moves code verbatim with contents changed only where a path is embedded.
- **Source:** harness plan principle P6; Phase 1 plan Global Constraints.
- **Enforcement:** review
- **Evidence:** the task report names each test and its red-then-green run; a move shows as a rename in git.

### ENG-WORK-3 — Write it down, do not re-prompt

- **Statement:** A correction needed twice becomes a gotcha, a rule, a skill line or a hook in the same commit.
- **Source:** harness plan principle P7.
- **Enforcement:** review
- **Evidence:** the handoff's rulings or `gotchas.md` carry the lesson.

## Documentation

### ENG-DOC-1 — Documentation discipline

- **Statement:** Repository documentation stays in English unless the owner asks otherwise, research reports are preserved, README lists real commands, and designs are updated when contracts or boundaries change.
- **Source:** AGENTS.md "Documentation and completion".
- **Enforcement:** review
- **Evidence:** README commands run; design sections cited by the change are current.

### ENG-DOC-2 — A handoff is complete

- **Statement:** A handoff states what changed, what was verified with its output, rulings with their cost if wrong, changes outside the repository with how to undo them, and what remains unimplemented.
- **Source:** AGENTS.md "Documentation and completion"; harness handoff schema.
- **Enforcement:** command
- **Evidence:** `uv run e-agent-harness handoff <task>` prints ok and the Markdown handoff has every section.
