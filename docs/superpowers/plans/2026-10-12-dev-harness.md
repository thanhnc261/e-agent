# Development harness for e-agent (phased plan)

> **For agentic workers:** this is a spec-level phased plan. Each phase gets a detailed plan (superpowers:writing-plans, saved to `docs/plans/` after roadmap Phase 1) before implementation. Phases marked `[OWNER]` stop for a decision first.

**Goal:** turn the way e-agent is built into a repeatable, checkable process, so that any agent session (Claude or Codex) follows the roadmap rules mechanically instead of from memory. The rules are:
- detailed plan first;
- design first;
- toggles with fallback;
- trust anchor unchanged;
- environment boundaries;
- per-task review;
- end-to-end verification.

Today these rules live in chat history and in reviewers' heads. The harness makes them files, schemas, checks and skills.

**Why:** across WP1 and the real-agent work, the expensive failures were process failures, not coding failures:
- a plan executed out of the design's order;
- live configuration that drifted from committed configuration;
- evidence files that did not match the committed tree;
- actions on shared Docker stacks blocked late;
- context lost across a session restart.

A harness pins context, scopes each task, runs the gates and records the evidence.

**Reference (concepts re-authored here, never imported or modified):** the owner's research harness in `/Users/thanhnguyen/dev/lab/onto-erp-agents/harness`. Its concepts include:
- a provider-neutral core;
- a context manifest whose content digest is pinned into every task, so a changed document invalidates the task;
- the loop INGEST → NORMALIZE → VALIDATE → PLAN → AWAIT_APPROVAL → MATERIALIZE → IMPLEMENT → VERIFY → REVIEW → REPAIR → CLOSE;
- plan, task, handoff and review JSON contracts;
- deterministic scope validation;
- policies that forbid automatic integration (merge, push, rebase);
- an independent reviewer who first sees the contract, diff and evidence, not the implementer's rationale;
- a human-facing status contract.

Nothing in that folder is copied without provenance, and nothing there is modified.

**Existing pieces to build on:**
- **UI skills:** the five `ag-*` skills in `.agents/skills/`, with `scripts/check_agent_skills.py` and `tests/conformance/test_agent_skills.py`.
- **Execution:** the superpowers subagent-driven workflow, with its ledger in the git-ignored `.superpowers/sdd/`.
- **Local permissions:** `.claude/settings.local.json`, which allows `odoo19-learning` and denies `odoo-bench`.

**Status:** Proposed. It runs as track H of the [roadmap](../../roadmap.md), alongside Phase 1.

## Global Constraints

- **Separate from the product.** The harness lives in `tools/harness/` (its own distribution, `e-agent-harness`). Product code never imports it; an import-linter contract enforces this. It is never a runtime dependency of the server.
- **Mechanical, not advisory.**
  - Scope, gates, protected paths and context digests are checked by code.
  - The harness never approves plans, changes specs, merges, pushes or rebases. Those actions stay with the owner (policy as code).
- **Provider-neutral.** Contracts and the CLI do not depend on Claude or Codex. Provider specifics live in thin adapters: `.claude/agents`, `.claude/settings.json` hooks and `.agents/skills`.
- **No secrets.** Evidence files are redacted. Live-check outputs never include keys.

## Phase H0: decisions `[OWNER]`

| Decision | Options | Recommendation |
|---|---|---|
| Harness size | (a) a lean e-agent harness: context manifest, contracts, scope and gate checks, skills, hooks; (b) port the full onto-erp harness, including the Omnigent orchestration and long-run launcher | (a). Grow it toward (b) only if long unattended runs become a need. |
| Orchestrator | Claude Code subagents (current); Omnigent (as in onto-erp) | Claude Code subagents now. Keep the contracts provider-neutral so Omnigent can drive them later. |
| Independent review | Same provider with a fresh context; or cross-provider (Claude implements, Codex reviews, as in onto-erp) | Cross-provider for trust-anchor and kernel tasks; a same-provider fresh context elsewhere |
| Human status language | English; Vietnamese ELI5 (as in onto-erp) | A Vietnamese ELI5 summary first, then English technical evidence |

## Phase H1: context manifest and contracts

**Deliverables:**
- **`harness/context.toml`** contains:
  - the ordered authoritative files: AGENTS.md, CLAUDE.md, `docs/roadmap.md`, `docs/design/*`, the ADR index, and the active phase plan;
  - protected paths: `archive/**` and `research/**` are read-only; `addons/**` changes require a bridge-version bump; secrets paths are deny-listed;
  - environment boundaries:
    - allowed containers: `odoo19-learning-*`, `e-agent-ledger`, and test containers the harness creates;
    - denied: `odoo-bench`, the `onto-erp-agents/experiment/**` and `enterprise-agent/experiment/**` paths, and the ERP-Bench `solution/**` and `tests/**`;
  - gate command sets: `quick` (one package), `full`, `pg`, `e2e`, `live`;
  - role → skill bindings.
- **`harness/contracts/*.schema.json`:**
  - `plan`: phase id, design refs, ADRs, toggles and fallback section, tasks;
  - `task`: id, pinned context digest, allowed paths, acceptance, gate set, base commit;
  - `handoff`: what changed, evidence refs, open items, rulings;
  - `review`: verdicts per finding, severity, evidence.
- **The digest rule:** a task stores the hash of every authoritative file. If any of them changes, the task is invalid and must be re-materialized.

**Exit:** `validate-context` passes on the repository, and the schemas validate the sample documents.

## Phase H2: harness CLI

`tools/harness` with commands (`uv run e-agent-harness <cmd>`):

| Command | Does |
|---|---|
| `validate-context` | Loads the manifest and checks that every authoritative file exists, that the protected-path globs are valid, and that the active plan named in the roadmap exists and has the required sections (design refs, toggles/fallback, review focus, gate). |
| `new-task <phase> <task>` | Materializes a task contract from the plan: allowed paths, acceptance, gate set, base commit, context digest. |
| `check-scope <task>` | Checks that the diff `base..HEAD` touches only the allowed paths, that no protected path changed, and that no file is staged outside the task. |
| `gate <set>` | Runs the gate set and writes `evidence/gates/<task>/<timestamp>.json`. The file records the commands, exit codes, test counts and the **commit SHA plus clean-tree flag**, so evidence can be tied to the committed tree (this addresses the e2e-evidence dispute in real-agent Task 6a). |
| `live-check` | Runs against `odoo19-learning`: identity check (`odoo_sandbox.py info`), plugin pin freshness (rebuilt wheels against the live profile), and stack readiness. It then runs the configured live flows and records run ids, states and reason codes, redacted. |
| `handoff <task>` | Validates the handoff document against its schema and checks that every evidence ref it cites exists. |
| `status` | Prints the human status contract: what was done, what completed, why it stopped, whether that stop was expected, the gate impact, and exactly one next action. A Vietnamese ELI5 summary comes first if chosen in H0. |

**Exit:**
- Each command has unit tests.
- `check-scope` rejects a planted out-of-scope change.
- `gate` produces evidence that matches `git rev-parse HEAD` on a clean tree.

## Phase H3: engineering skills (next to the `ag-*` UI skills)

`.agents/skills/eng-*`, linked from `.claude/skills/` as the `ag-*` skills are, and validated by an extended `scripts/check_agent_skills.py`:

| Skill | Purpose |
|---|---|
| `eng-foundations` | The engineering standard: architecture rules, trust anchor, toggles and fallback, both stores, import contracts, evidence discipline. Cited by ID, as `ag-ux-foundations` is. |
| `eng-phase-plan` | Roadmap phase → detailed plan in `docs/plans/`. Mandatory sections: design refs, ADRs, toggles and fallback, review focus, gate, live check. Stops for owner review. |
| `eng-implement` | Task contract → test-first implementation. Verbatim moves for refactors. Gate through the harness. Report with evidence refs. |
| `eng-review` | Task and phase review rubric: spec, trust-anchor invariants, toggle and fallback correctness, both stores, link and path hygiene, evidence tied to the commit. Produces a review JSON. |
| `eng-verify` | Full gate, then `make e2e`, then the live check. Refuses evidence from a dirty tree. |
| `eng-adr` | ADR authoring and index update, with status rules (Proposed is not baseline). |
| `eng-handoff` | Handoff document: changes, evidence, changes outside the repository with how to undo them, rulings with their cost if wrong, open owner decisions. |
| `live-sandbox` | `odoo19-learning` operations: bridge upgrade with `-u`, seed and reset with identity flags, wheel re-pin, live stack start. Hard deny on `odoo-bench`. |

**Exit:**
- `check_agent_skills.py` validates all `eng-*` skills.
- A scenario fixture per skill, as the `ag-*` skills have, demonstrates the stop gates.

## Phase H4: Claude Code and Codex integration

| Deliverable | Content |
|---|---|
| `.claude/agents/implementer.md`, `reviewer.md`, `verifier.md` | Role prompts that load the matching `eng-*` skill. The reviewer receives the contract, diff and evidence, not the implementer's rationale, on its first pass. Model tiers are documented. |
| `.claude/settings.json` (committed) | `PreToolUse` hooks that deny: Docker commands on containers outside the allowed list; writes under `archive/` and `research/`; reads of ERP-Bench `solution/` and `tests/`; `git push`, `merge` and `rebase` without explicit owner instruction. Project permission rules allow `odoo19-learning` compose and exec, replacing today's local-only file. |
| Stop and session hooks | At session start, print `e-agent-harness status`, so context survives restarts (the gap seen after the real-agent session restart). |
| Codex parity | AGENTS.md points to the same skills and the harness CLI. Codex follows the same contracts. |

**Exit:**
- A planted Docker command against `odoo-bench` is denied by the hook.
- A fresh session prints the status of the current phase.
- Codex can run `eng-review` on a task package.

## Phase H5: pilot and adoption

- **Pilot:** run roadmap Phase 1c (kernel split) end to end through the harness:
  1. task contracts;
  2. scope check;
  3. gate evidence;
  4. review JSON;
  5. handoff.
- **Measure:**
  - rework rounds;
  - evidence disputes;
  - boundary violations, which should be zero;
  - time per task.
- **Adopt** for Phase 2 onward. The roadmap Rules then reference the harness commands instead of prose.

## Phase map

| Phase | Size | Depends on | Owner gates |
|---|---|---|---|
| H0 Decisions | 1 | none | 4 decisions |
| H1 Manifest and contracts | 3 | H0; roadmap Phase 1b (doc paths) | none |
| H2 CLI | 7 commands | H1 | none |
| H3 Engineering skills | 8 skills | H1 | skill review |
| H4 Claude and Codex integration | 4 | H2, H3 | hooks review |
| H5 Pilot | 1 phase run | H4; roadmap Phase 1c | adoption |
