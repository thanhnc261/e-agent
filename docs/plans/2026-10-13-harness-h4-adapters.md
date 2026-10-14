# Harness H4: Claude Code adapters

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** wire the harness into Claude Code so the session loop runs without being remembered: a committed `.claude/settings.json` with permissions, hooks and context settings, a hook entry script, and four subagents that preload the `eng-*` skills.

**Architecture:** every hook calls one stdlib-only script, `.claude/hooks/harness_hook.py`, which finds the repository from the hook payload's `cwd` (a worktree has its own) and runs `uv run --directory <repo> e-agent-harness <command>` with the payload on stdin. Hard rules are permission rules (deny, ask); conditional checks are hooks. Subagents live in `.claude/agents/`. Codex has no hooks: it runs the same commands by hand from `eng-session`.

**Status:** Done 2026-10-14; tasks H4.1 to H4.6, review fixes H4.R1 to H4.R15 and H4.16 ([handoff](../handoffs/2026-10-13-harness-h4.md)).

**Tech Stack:** Claude Code settings, hooks and subagents; Python 3.12 stdlib; pytest.

**Spec:** [harness plan](2026-10-12-dev-harness.md) section "Phase H4" and "Context strategy"; H0 decisions (auto-compact window 400K, unattended runs from Phase 2, cross-provider review); Claude Code docs for settings, permissions, hooks and subagents (read 2026-10-13).

## Global Constraints

- Branch `harness/h4-adapters` from `main` at `9817a85`; trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The work runs as harness phase `H4`: features in `harness/state/H4/features.json`, one contract per task, `gate full`, `close-check`.
- Hooks are fast and never trap an attended session: `status` and `checkpoint` hooks always exit 0; `check-scope` fails closed (exit 2); `close-check` blocks only when `E_AGENT_HARNESS_UNATTENDED=1`.
- Hard rules are permission rules: `odoo-bench` and the protected research inputs are denied; `git push`, `git merge`, `git rebase` and `git reset --hard` ask the owner.
- No container is touched. Live checks run in a scratch clone with `claude -p`.
- User-specific allow rules (paths under the owner's home) stay in `.claude/settings.local.json`, which is not committed.

## Review Focus

1. **A session started in a worktree.** The hook must use the worktree's harness state, not the main checkout's. Test: H4.1 `test_wrapper_uses_the_payload_cwd_repository`.
2. **No repository or no `uv` on the path.** `check-scope` must deny (fail closed); `status` and `checkpoint` must exit 0 silently. Test: H4.1 `test_wrapper_failure_modes`.
3. **A permission rule that does not match the real command shape** (for example `docker exec odoo-bench-db-1 …`). Test: H4.2 `test_deny_rules_cover_odoo_bench_shapes`.
4. **An edit through Bash** is not seen by the `Edit|Write` hook; `check-scope` before each commit stays the guard. Documented in `eng-session`.
5. **A subagent that preloads a skill marked `disable-model-invocation`** fails to load it. Test: H4.3 `test_agents_preload_only_invocable_skills`.

---

### Task H4.1: hook entry script

**Files:** `.claude/hooks/harness_hook.py`, `tests/harness/test_hook_wrapper.py`.

- [x] Failing tests: the script runs `check-scope --hook` and denies an out-of-scope `Write` (exit 2, reason on stderr); allows an in-scope one; `status --format hook` prints SessionStart JSON; `checkpoint --hook` appends an entry; with a payload `cwd` outside any repository `check-scope` exits 2 and the others exit 0; `format` runs the formatter on an edited `.py` file and always exits 0; the repository is found from the payload `cwd`.
- [x] Implement; commit `feat(harness): hook entry script for Claude Code`.

### Task H4.2: `.claude/settings.json`

**Files:** `.claude/settings.json`, `tests/conformance/test_claude_settings.py`.

- [x] Failing tests: valid JSON; `autoCompactWindow` 400000; `worktree.baseRef` `"head"`; deny rules cover `docker compose -p odoo-bench`, `docker exec odoo-bench*`, stop, restart, rm, kill, `Edit(archive/**)` and the ERP-Bench `solution/` and `tests/` reads; ask rules cover `git push`, `git merge`, `git rebase`, `git reset --hard`; allow rules cover the `odoo19-learning` compose, exec and logs; hooks: `SessionStart` (startup, resume, clear, compact) → `status --format hook`, `PreCompact` → `checkpoint --hook`, `PreToolUse` `Edit|Write|NotebookEdit` → `check-scope --hook`, `PostToolUse` `Edit|Write` → `format`, `Stop` → `close-check --hook`; every hook command calls the entry script with a timeout.
- [x] Implement; commit `feat(harness): committed Claude Code settings (permissions, hooks, compaction, worktrees)`.

### Task H4.3: subagents

**Files:** `.claude/agents/explorer.md`, `verifier.md`, `reviewer.md`, `sandbox-operator.md`, `tests/conformance/test_claude_agents.py`.

- [x] Failing tests: each agent has `name` equal to its file name and a short `description`; `explorer`, `verifier` and `reviewer` cannot edit (`disallowedTools` includes `Edit`, `Write`, `NotebookEdit`); preloaded skills exist and none has `disable-model-invocation: true`; the reviewer is never a fork; combined descriptions stay short.
- [x] Implement; commit `feat(harness): explorer, verifier, reviewer and sandbox-operator subagents`.

### Task H4.4: live verification and docs

- [x] In a scratch clone of the branch: `claude -p` reports the SessionStart brief's next action without using tools; `claude -p --permission-mode dontAsk --allowedTools Write` asked to write a file outside the contract is denied by the hook and the file does not exist.
- [x] Docs: `eng-session` (hooks now run the start brief, checkpoint before compaction and scope checks; edits through Bash are not hooked), README, AGENTS.md one line, harness plan H4 done line, handoff `docs/handoffs/2026-10-13-harness-h4.md`.
- [x] Commit `docs(harness): H4 live verification, skills and handoff`.

### Task H4.5: research accepts new files (owner decision 2026-10-13)

**Files:** `tools/harness/…/manifest.py`, `scope.py`, `gitinfo.py`, `harness/context.toml`, `eng-foundations` ENG-BOUND-2, tests.

- [x] Manifest `[protected] create_only = ["research/**"]`: a path that is read-only and create-only may be written when it is not tracked at the task's base commit (or at HEAD without a task). Existing studies stay as written; a new file still needs the open task's scope.

### Task H4.6: tidy replaces the per-edit format hook (owner decision 2026-10-13)

- [x] `e-agent-harness tidy` runs `ruff check --fix` and `ruff format` once over the change (working tree plus commits since the task base), runs the UI's scoped formatter when `ui/` changed, and reports what it cannot fix (exit 1). The `PostToolUse` format hook and the script's format mode are removed: formatting after each edit made Claude's view of the file stale and never linted; the gate stays the check. `eng-session` runs `tidy` before the commit.

## Deferred

- The test-output filter hook and the reviewer `SubagentStop` validation: the `validate` command covers the review JSON; add the hooks when a phase needs them.
