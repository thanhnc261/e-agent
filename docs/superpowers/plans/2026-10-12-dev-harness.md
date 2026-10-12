# Development harness for e-agent (phased plan)

> **For agentic workers:** this is a spec-level phased plan. Each phase gets a detailed plan (superpowers:writing-plans, saved to `docs/plans/` after roadmap Phase 1) before implementation. Phases marked `[OWNER]` stop for a decision first.

**Goal:** turn the way e-agent is built into a repeatable, checkable **local development loop** that survives context resets and session restarts, so that any agent session (Claude or Codex) follows the roadmap rules mechanically instead of from memory. The rules are:
- detailed plan first;
- design first;
- toggles with fallback;
- trust anchor unchanged;
- environment boundaries;
- per-task review;
- end-to-end verification.

Today these rules live in chat history and in reviewers' heads. The harness makes them files, schemas, checks, hooks and skills.

**Why:** across WP1 and the real-agent work, the expensive failures were process failures, not coding failures:
- a plan executed out of the design's order;
- live configuration that drifted from committed configuration;
- evidence files that did not match the committed tree;
- actions on shared Docker stacks blocked late;
- context lost across a session restart and across compaction.

A harness pins context, scopes each task, runs the gates, records the evidence and hands the next session a brief it can trust.

**What the harness is:** durable state on disk (the only memory that survives a context window), a small provider-neutral CLI that checks that state, and thin adapters onto Claude Code's own primitives: CLAUDE.md and rules, permission rules, hooks, subagents, worktrees, `/goal`. It is a loop for one owner and a few agent sessions. It is **not** a CI platform, an orchestration framework or a multi-team control plane; none of those is needed for this project and each would cost context and attention.

**Existing pieces to build on:**
- **UI skills:** the five `ag-*` skills in `.agents/skills/`, with `scripts/check_agent_skills.py` and `tests/conformance/test_agent_skills.py`.
- **Execution:** the superpowers subagent-driven workflow, with its ledger in the git-ignored `.superpowers/sdd/`.
- **Local permissions:** `.claude/settings.local.json`, which allows `odoo19-learning` and denies `odoo-bench`.
- **Gates:** `make e2e`, `scripts/env_check.py`, `scripts/odoo_sandbox.py`, the git-ignored `evidence/` folder.

**Status:** Accepted 2026-10-12 (H0 decided); H1 in progress. It runs as track H of the [roadmap](../../roadmap.md), alongside Phase 1.

## Principles from the sources

The design below is derived from Anthropic's published harness and context-engineering work and from the Claude Code documentation (see [Sources](#sources)). Each principle names the mechanism that enforces it here; a principle without a mechanism is advice, and advice is what failed before.

| # | Principle | Source | Mechanism in e-agent |
|---|---|---|---|
| P1 | **Artifacts on disk are the memory.** Each session starts by reading them and ends by updating them; nothing that matters lives only in the conversation. | Effective harnesses for long-running agents; context engineering (structured note-taking) | Feature list, progress log, task contract, handoff, evidence files; `status` printed by a SessionStart hook on `startup`, `resume`, `clear` and `compact`. |
| P2 | **Three failure modes of long work:** doing too much at once, declaring victory early, marking work done without verification. | Effective harnesses for long-running agents | One task per context window; `passes` in the feature list flips only with a gate evidence reference; a verifier that reports and does not fix. |
| P3 | **Each stage commits an artifact the next stage reads; the commit history is the audit trail.** When implementation diverges, the plan is updated in the same commit. | AI-native SDLC playbook | `docs/plans/<phase>.md` → task contract → evidence → review JSON → handoff. `close-check` fails when a diverged plan was not updated. |
| P4 | **Advisory versus mandatory.** CLAUDE.md and skills advise; permission rules and hooks enforce. | AI-native SDLC playbook; Claude Code memory and hooks docs | Every "never" in AGENTS.md becomes a `permissions.deny` rule or a hook with exit 2. |
| P5 | **Context is a finite attention budget.** Load the smallest set of high-signal tokens; use compaction, notes on disk and subagents for long horizons. | Effective context engineering for AI agents; Claude Code best practices | The [context strategy](#context-strategy) table; a token budget on `status`; subagents for reads, test runs and logs. |
| P6 | **Verification is the highest-leverage practice, and the agent that wrote the code does not grade it.** A standalone evaluator is far easier to make sceptical than a generator is to make self-critical. | Claude Code best practices; harness design for long-running apps | `gate` writes evidence tied to the commit; `verifier` and `reviewer` subagents run in fresh contexts and see the contract, diff and evidence, not the rationale; cross-provider review for the trust anchor. |
| P7 | **Write it down, don't re-prompt.** The same mistake twice becomes a rule, a skill or a hook, because a chat correction fixes one run and a file fixes every future run. | Boris Cherny's tips (fan-made collection); SDLC playbook | A retro line in the close ritual; `eng-foundations` keeps a gotchas section; `/doctor prompt-audit` in H5. |
| P8 | **Each harness component encodes an assumption about what the model cannot do alone.** Re-examine the harness with each new model and remove what is no longer load-bearing. | Harness design for long-running apps | H5 harness review rule; the phase map keeps H4 adapters thin so they can be dropped. |

## Standard session loop

This is the local dev loop every task follows, attended or not. The `eng-session` skill (H3) states it; the hooks and CLI (H2, H4) enforce the steps marked ⚙.

**Start ritual**
1. ⚙ `e-agent-harness status` runs from the SessionStart hook and prints: current phase and plan, the active task contract with its allowed paths and gate set, the last progress entries, the boundary reminders (allowed containers, protected paths) and **exactly one next action**. Budget: about 1,500 tokens; the hook output is the session brief.
2. Confirm where you are: `pwd`, `git status`, `git log -5`. Edits are limited to the current checkout or worktree.
3. ⚙ Smoke check before new work: `gate quick` on the task's package, or `scripts/env_check.py` for live work. A failing smoke check is the first task; nothing new starts on a broken base.
4. Pick exactly one task: the active contract, or `new-task` for the highest-priority unfinished entry in the phase's feature list. If the contract's context digest is stale, re-materialise it first.

**Work**
5. Research through the `explorer` subagent, not in the main context. The main context holds the contract, the plan section and the files being changed.
6. Test first. Implement only inside the contract's allowed paths (⚙ `check-scope` hook denies the rest). Refactors are verbatim moves.
7. ⚙ Checkpoint at natural breaks: `checkpoint` appends what changed and what is next to the progress log. `PreCompact` runs it automatically, so compaction never loses the task state.

**Close ritual**
8. ⚙ `gate <set>` writes `evidence/gates/<task>/<timestamp>.json` with commands, exit codes, counts, the commit SHA and the clean-tree flag.
9. `verifier` subagent re-runs the acceptance steps and returns a short JSON report with the evidence path; it never edits. `reviewer` subagent reviews the contract, the diff and the evidence and returns review JSON. Findings that affect correctness or the contract are fixed and re-reviewed; the rest are optional.
10. Commit with a descriptive message. ⚙ `close-check`: tree clean, progress log updated this session, feature `passes` flipped only with an evidence reference, handoff validated, plan updated if the task diverged.
11. Retro line (P7): if the same correction was needed twice, add the rule, skill line or hook in the same commit.
12. End the context: `/clear`, then the next session's brief is the `status` output. Compaction is for mid-task continuity only, never for starting the next task.

**Unattended variant** (allowed per H0): a task runs as `claude --worktree task-<id> -p "<brief>"` with `/goal "<acceptance, demonstrated by gate output> or stop after N turns"`, a budget (`--max-budget-usd`), `--permission-mode dontAsk` plus the committed allowlist, and the Stop hook running `close-check`. The goal evaluator judges only what appears in the transcript, so acceptance must be shown by the gate command's output, not asserted.

## Context strategy

| Situation | Do | Mechanism |
|---|---|---|
| Starting a new task | `/clear`, then the `status` brief | SessionStart hook on `clear`; `eng-session` |
| Long task, context filling | `/compact <focus>` at a natural break, not when the auto-compact fires mid-edit | `checkpoint` from `PreCompact`; SessionStart hook on `compact` re-injects `status`; a `# Compact instructions` section in CLAUDE.md names what the summary must keep (contract id, modified files, gate commands, open findings) |
| Auto-compact window | Set lower than the model default, so compaction happens before quality degrades | `autoCompactWindow` in `.claude/settings.json` or `CLAUDE_CODE_AUTO_COMPACT_WINDOW`; the value is an H0 decision. On 1M-window models the default is about 967K tokens | 400K tokens, committed in `.claude/settings.json` (H4). |
| Reading many files, running tests, reading logs | Delegate to a subagent that returns a short summary plus an evidence path | `explorer` and `verifier` agents; a `PreToolUse` Bash hook that filters test output to failures |
| Two failed corrections on one issue | `/rewind` to the checkpoint before the first attempt, or `/clear` with a better brief | Claude Code checkpoints; the brief is `status` plus the lesson |
| Parallel tasks | One worktree per task, branched from the current feature branch | `worktree.baseRef: "head"` in settings; `.worktreeinclude` for `.env` and local profiles; `.claude/worktrees/` already git-ignored |
| Invariants that must survive compaction (trust anchor, boundaries, both stores) | Keep them in the root CLAUDE.md or AGENTS.md import and in unscoped `.claude/rules/` | Only the root instruction files, unscoped rules, auto memory, the plan-mode plan, the five most recently modified files and capped skill bodies are re-injected after compaction. Path-scoped rules and nested CLAUDE.md are summarised away |
| Skills on the critical path | Put the critical instructions at the top of `SKILL.md` | Invoked skill bodies are re-injected after compaction capped at 5,000 tokens each and 25,000 in total, truncated from the end |
| Model and effort | Choose at the top of a session; avoid mid-task switches | A model switch invalidates the prompt cache; effort changes keep it on Fable 5.1 and the 5.5 models |
| Side questions | `/btw` | The answer never enters the conversation |
| Subagent results | Return structured, short results (JSON with an evidence path), never raw logs | Subagent output lands in the main context |

## Global Constraints

- **Separate from the product.** The harness lives in `tools/harness/` (its own distribution, `e-agent-harness`). Product code never imports it; an import-linter contract enforces this. It is never a runtime dependency of the server.
- **Mechanical, not advisory.**
  - Scope, gates, protected paths and context digests are checked by code.
  - The harness never approves plans, changes specs, merges, pushes or rebases. Those actions stay with the owner (policy as code: permission deny rules).
- **Provider-neutral core, thin adapters.** Contracts and the CLI do not depend on Claude or Codex. Provider specifics live in `.claude/agents`, `.claude/settings.json` hooks and permissions, and `.agents/skills`. No custom orchestrator: Claude Code's subagents, worktrees, `/goal` and `/batch` are the orchestration.
- **No secrets.** Evidence files are redacted. Live-check outputs never include keys.
- **Token discipline.** `status` has a budget; hooks inject facts, not instructions; subagents return summaries.

## Phase H0: decisions `[OWNER]` (decided 2026-10-12)

| Decision | Options | Recommendation | Decided 2026-10-12 |
|---|---|---|---|
| Harness size | (a) lean: manifest, contracts, CLI checks, skills, hooks and agents; (b) a full orchestrator with its own run loop | (a). Claude Code already provides the loop primitives; add (b) only if long unattended runs become routine. | Lean (a). |
| Independent review | Same provider in a fresh subagent; or cross-provider (Claude implements, Codex reviews) | Cross-provider for trust-anchor and kernel tasks; a same-provider fresh subagent elsewhere. | Cross-provider: Codex reviews trust-anchor and kernel tasks; same-provider fresh subagent elsewhere. |
| Human status language | English; Vietnamese ELI5 first | A Vietnamese ELI5 summary first, then English technical evidence. | Vietnamese ELI5 first, then English evidence. |
| Unattended runs | Attended only; or unattended per task, in a worktree, with a budget and `close-check` as the Stop gate | Attended for the H5 pilot; unattended allowed from roadmap Phase 2 for mechanical tasks (verbatim moves, migrations). | Attended for the H5 pilot; unattended from roadmap Phase 2 for mechanical tasks. |
| Auto-compact window | Model default; or a lower fixed window | A lower window. The number is the owner's; the plan records it in `.claude/settings.json`. | 400K tokens, committed in `.claude/settings.json` (H4). |
| Instruction loading | `@AGENTS.md` import in CLAUDE.md; or the `claude-md-and-agents-md` project-instructions setting | The import. It is committed, works for every machine and keeps one shared file for Codex. | The `@AGENTS.md` import. |

## Phase H1: durable state and instruction files

**Deliverables:**
- **`harness/context.toml`** contains:
  - the ordered authoritative files: AGENTS.md, CLAUDE.md, `docs/roadmap.md`, the design documents (paths as they are after roadmap Phase 1b), the ADR index, and the active phase plan;
  - protected paths: `archive/**` and `research/**` are read-only; `addons/**` changes require a bridge-version bump; secrets paths are deny-listed;
  - environment boundaries:
    - allowed containers: `odoo19-learning-*`, `e-agent-ledger`, and test containers the harness creates;
    - denied: `odoo-bench`, the `enterprise-agent/experiment/**` path, and the ERP-Bench `solution/**` and `tests/**`;
  - gate command sets: `quick` (one package), `full`, `pg`, `e2e`, `live`;
  - role → skill bindings;
  - the `status` token budget.
- **`harness/contracts/*.schema.json`:**
  - `plan`: phase id, design refs, ADRs, toggles and fallback section, tasks;
  - `task`: id, pinned context digest, allowed paths, acceptance steps, gate set, base commit;
  - `features`: per phase, entries with `id`, `category`, `description`, ordered end-to-end `steps`, `passes` (starts `false`) and `evidence` (required when `passes` is true). JSON, not Markdown, because agents are less likely to rewrite it casually;
  - `progress`: the progress log format (session id, task id, what changed, what is next, open items), append-only;
  - `handoff`: what changed, evidence refs, open items, rulings, changes outside the repository and how to undo them;
  - `review`: verdicts per finding, severity, evidence.
- **The digest rule:** a task stores the hash of every authoritative file. If any of them changes, the task is invalid and must be re-materialised.
- **Instruction-file fix.** Finding: `CLAUDE.md` links to `AGENTS.md` with a Markdown link, not an `@AGENTS.md` import, and Claude Code reads `AGENTS.md` directly only when no `CLAUDE.md` exists. In the current checkout a Claude session therefore loads the seven-line `CLAUDE.md` and not the shared rules unless it reads them by hand. Deliverable: the import (per H0), verified with `/context`. `AGENTS.md` is 64 lines, inside the documented 200-line guidance; keep it there by moving procedures into `eng-*` skills and keeping only invariants, commands and boundaries in the root files, so they survive compaction. Add a `# Compact instructions` section. No `.claude/rules/` directory (decided in H1): the imported `AGENTS.md` is project context and is re-injected after compaction already, and path-scoped rules would be summarised away.
- **Status contract text:** what was done, what completed, why it stopped, whether that stop was expected, the gate impact, and exactly one next action.

**Done 2026-10-12** (branch `harness/h1-durable-state`, [handoff](../../handoffs/2026-10-12-harness-h1.md)): [`harness/context.toml`](../../../harness/context.toml), schemas under `tools/harness/src/e_agent_harness/schemas/`, samples under `harness/samples/`, modules `manifest`, `digest`, `contracts`, `progress` in the `e-agent-harness` distribution, and `tests/conformance/test_harness_context.py`. The `validate-context` command itself is H2; H1 ships the function it wraps.

**Exit:**
- `validate_manifest` returns no problems on the repository, and the schemas validate the sample documents (conformance test).
- A fresh `claude -p` session answers from the imported `AGENTS.md` (checked 2026-10-12); `/doctor prompt-audit` is run by the owner in an interactive session.

## Phase H2: harness CLI

`tools/harness` with commands (`uv run e-agent-harness <cmd>`). Commands that hooks call accept the hook's JSON on stdin and read the working directory from its `cwd` field, because `${CLAUDE_PROJECT_DIR}` stays at the main checkout inside a worktree.

| Command | Does |
|---|---|
| `validate-context` | Loads the manifest and checks that every authoritative file exists, that the protected-path globs are valid, and that the active plan named in the roadmap exists and has the required sections (design refs, toggles/fallback, review focus, gate). |
| `new-task <phase> <task>` | Materialises a task contract from the plan and the feature list: allowed paths, acceptance steps, gate set, base commit, context digest. |
| `check-scope [<task>]` | Checks that the diff `base..HEAD` plus the working tree touches only the allowed paths, that no protected path changed, and that no file is staged outside the task. As a `PreToolUse` hook it checks the single path of an `Edit`, `Write` or `NotebookEdit` call and exits 2 with the reason. |
| `gate <set>` | Runs the gate set and writes `evidence/gates/<task>/<timestamp>.json`: commands, exit codes, test counts, the **commit SHA plus clean-tree flag**, so evidence is tied to the committed tree (the e2e-evidence dispute in real-agent Task 6a). |
| `live-check` | Runs against `odoo19-learning`: identity check (`odoo_sandbox.py info`), plugin pin freshness (rebuilt wheels against the live profile), stack readiness, then the configured live flows; records run ids, states and reason codes, redacted. |
| `checkpoint` | Appends a progress entry (task, modified files from `git status`, next step from the contract or an argument). Called by `PreCompact` and at natural breaks. |
| `close-check` | Fails unless: the tree is clean, the progress log has an entry for this session, every `passes: true` flipped in this task cites an evidence file whose SHA matches HEAD, the handoff validates, and the plan was updated if the contract's acceptance changed. Used by the Stop hook in unattended runs. |
| `handoff <task>` | Validates the handoff document against its schema and checks that every evidence ref it cites exists. |
| `status [--format text\|hook]` | Prints the human status contract (Vietnamese ELI5 first if chosen in H0). `--format hook` emits the SessionStart `additionalContext` JSON with a `sessionTitle`, within the manifest's token budget, written as facts rather than imperatives. |

**Exit:**
- Each command has unit tests.
- `check-scope` rejects a planted out-of-scope change, both as a command and as a hook.
- `gate` produces evidence that matches `git rev-parse HEAD` on a clean tree; `close-check` rejects a `passes` flip without evidence.
- `status --format hook` stays within its budget on the real repository.

## Phase H3: engineering skills (next to the `ag-*` UI skills)

`.agents/skills/eng-*`, linked from `.claude/skills/` as the `ag-*` skills are, and validated by an extended `scripts/check_agent_skills.py`. Critical instructions go at the top of each `SKILL.md` (compaction truncates from the end); skills with side effects set `disable-model-invocation: true`.

| Skill | Purpose |
|---|---|
| `eng-session` | The [standard session loop](#standard-session-loop): start ritual, one task, close ritual, context strategy. Loaded by the implementer role and by the owner's own sessions. |
| `eng-foundations` | The engineering standard: architecture rules, trust anchor, toggles and fallback, both stores, import contracts, evidence discipline, and a gotchas section fed by the retro line. Cited by ID, as `ag-ux-foundations` is. |
| `eng-phase-plan` | Roadmap phase → detailed plan in `docs/plans/` plus the phase feature list. Mandatory sections: design refs, ADRs, toggles and fallback, review focus, gate, live check. Stops for owner review. |
| `eng-implement` | Task contract → test-first implementation. Verbatim moves for refactors. Gate through the harness. Report with evidence refs. |
| `eng-review` | Task and phase review rubric: spec, trust-anchor invariants, toggle and fallback correctness, both stores, link and path hygiene, evidence tied to the commit. Produces review JSON; flags only findings that affect correctness or the contract. |
| `eng-verify` | Full gate, then `make e2e`, then the live check. Refuses evidence from a dirty tree. |
| `eng-adr` | ADR authoring and index update, with status rules (Proposed is not baseline). |
| `eng-handoff` | Handoff document: changes, evidence, changes outside the repository with how to undo them, rulings with their cost if wrong, open owner decisions. |
| `live-sandbox` | `odoo19-learning` operations: bridge upgrade with `-u`, seed and reset with identity flags, wheel re-pin, live stack start. Hard deny on `odoo-bench` stays in permissions; the skill only documents the allowed commands. Manual invocation only. |

**Exit:**
- `check_agent_skills.py` validates all `eng-*` skills.
- A scenario fixture per skill, as the `ag-*` skills have, demonstrates the stop gates.

## Phase H4: Claude Code and Codex adapters

| Deliverable | Content |
|---|---|
| `.claude/settings.json` (committed) | **Permissions** (hard rules belong here, not in hooks): allow `odoo19-learning` compose, exec and logs (moved from the local file); deny `odoo-bench` compose, exec, stop, restart, rm, kill; deny `Bash(git push *)`, `Bash(git merge *)`, `Bash(git rebase *)`; deny `Read` of the ERP-Bench `solution/**` and `tests/**` paths and of `enterprise-agent/experiment/**`. **Settings:** `worktree.baseRef: "head"`, `autoCompactWindow` per H0. |
| Hooks | `SessionStart` (matchers `startup`, `resume`, `clear`, `compact`) → `status --format hook`. `PreCompact` → `checkpoint`. `PreToolUse` on `Edit\|Write\|NotebookEdit` → `check-scope` (exit 2 on violation). `PreToolUse` on `Bash` → container guard against the manifest's allowed list for `docker` commands (conditional logic; the hard deny is the permission rule) and the test-output filter that rewrites `pytest`/`pnpm test` to show failures only. `PostToolUse` on `Edit\|Write` → formatter on the changed file only (`ruff format`, `prettier`). `Stop` → `close-check`, enabled only when `E_AGENT_HARNESS_UNATTENDED=1`, so attended sessions are never trapped. `SubagentStop` for the reviewer → validates the review JSON. All hooks are fast and scoped to one file; the heavy checks stay in `gate`. |
| `.claude/agents/explorer.md`, `verifier.md`, `reviewer.md`, `sandbox-operator.md` | `explorer`: read-only tools, a smaller model, returns a summary with file paths. `verifier`: `Bash` and `Read` only, `disallowedTools: Edit, Write`, `maxTurns` set, preloads `eng-verify`, returns schema'd JSON with the evidence path. `reviewer`: read-only tools, the strongest available model, preloads `eng-review`, returns review JSON; it is a normal (non-fork) subagent, so it never sees the implementer's reasoning, only the contract, diff and evidence named in its task. `sandbox-operator`: preloads `live-sandbox`, tools limited to the allowed container commands, `permissionMode` left to the session. Each agent carries a short `description` so the combined roster stays small. |
| Parallel and batch work | One worktree per task (`claude --worktree task-<id>`); `.worktreeinclude` lists `.env` and local profiles. Roadmap Phase 1a verbatim moves run through `/batch` on one package first, then the rest, each subagent in its own worktree. |
| Unattended recipe | Documented in `eng-session`: the command line, the `/goal` wording (acceptance shown by gate output, a turn cap), the budget flag, and the Stop-hook gate. Results arrive as a handoff, never as a push. |
| Codex parity | AGENTS.md is the shared instruction file; the CLI is provider-neutral. Codex runs `eng-review` on a task package (contract, diff, evidence) and writes the same review JSON. |

**Exit:**
- A planted Docker command against `odoo-bench` is denied by the permission rule; a planted write under `archive/` and a planted edit outside the task's paths are denied by the hook.
- A fresh session, a resumed session and a post-compaction session each show the status brief.
- Codex produces a valid review JSON on a task package.

## Phase H5: pilot and adoption

- **Pilot:** run roadmap Phase 1c (kernel split) end to end through the loop:
  1. feature list and task contracts;
  2. scope check;
  3. gate evidence;
  4. verifier and reviewer reports;
  5. handoff and `close-check`.
- **Measure:**
  - rework rounds per task;
  - evidence disputes;
  - boundary violations (should be zero);
  - repeated corrections that should have become a rule (P7);
  - tokens per task and context resets per task, from `/usage` and the progress log.
- **Adopt** for Phase 2 onward. The roadmap Rules then reference the harness commands instead of prose.
- **Harness review rule (P8):** on each model change, and at least once per roadmap phase, re-run `/checkup` and `/doctor prompt-audit`, and drop any hook, agent or skill that no longer prevents a failure the pilot measured.

## Phase map

| Phase | Size | Depends on | Owner gates |
|---|---|---|---|
| H0 Decisions | 1 | none | 6 decisions |
| H1 Durable state and instruction files | 4 | H0; roadmap Phase 1b (doc paths) | none |
| H2 CLI | 9 commands | H1 | none |
| H3 Engineering skills | 9 skills | H1 | skill review |
| H4 Claude and Codex adapters | 5 | H2, H3 | hooks and permissions review |
| H5 Pilot | 1 phase run | H4; roadmap Phase 1c | adoption |

## Sources

Read first-hand on 2026-10-12. The Claude Code pages describe current behaviour and change often; re-check version notes before relying on a specific threshold.

- Anthropic, [The AI-native SDLC playbook](https://claude.com/resources/articles/the-ai-native-sdlc-playbook): committed artifacts per stage, CLAUDE.md under a page, skills advisory and hooks mandatory, verifier subagent, hooks as approval gates.
- [How Boris uses Claude Code](https://howborisusesclaudecode.com/): a fan-made collection of Boris Cherny's tips, not an Anthropic publication. Used for the verification emphasis, `/clear` plus a brief over `/compact`, the auto-compact window, worktrees, and "write it down, don't re-prompt".
- Anthropic Engineering, [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents): feature list with `passes`, progress file, init script, git discipline, the three failure modes, session start and end rituals.
- Anthropic Engineering, [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps): planner, generator and evaluator; evaluator independence; file-based communication; components encode assumptions about the model.
- Anthropic Engineering, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents): attention budget, just-in-time retrieval, compaction, structured note-taking, sub-agent architectures.
- Claude Code docs: [Best practices](https://code.claude.com/docs/en/best-practices), [Explore the context window](https://code.claude.com/docs/en/context-window) (what survives compaction), [How Claude remembers your project](https://code.claude.com/docs/en/memory) (CLAUDE.md, AGENTS.md, rules, 200-line guidance), [Manage costs](https://code.claude.com/docs/en/costs), [Model configuration](https://code.claude.com/docs/en/model-config) (auto-compact window, effort), [Prompt caching](https://code.claude.com/docs/en/prompt-caching), [Subagents](https://code.claude.com/docs/en/sub-agents), [Hooks reference](https://code.claude.com/docs/en/hooks), [/goal](https://code.claude.com/docs/en/goal), [Scheduled tasks and /loop](https://code.claude.com/docs/en/scheduled-tasks), [Worktrees](https://code.claude.com/docs/en/worktrees), [Sessions](https://code.claude.com/docs/en/sessions), [Dynamic workflows](https://code.claude.com/docs/en/workflows).
