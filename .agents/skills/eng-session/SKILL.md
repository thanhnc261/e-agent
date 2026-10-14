---
name: eng-session
description: The engineering session loop; use at session start and before closing any task.
---

# Engineering session

One task per context window, every step checkable by the harness. The commands are `uv run e-agent-harness <cmd>`; `status` always names the single next action.

## Hard limits

- Read [eng-foundations](../eng-foundations/SKILL.md) first; cite rules by ID.
- One task per context window inside its contract's allowed paths (ENG-WORK-1). The next task starts in a cleared context.
- Nothing new starts on a failing smoke check. A failing smoke check is the first task.
- Evidence is recorded on a clean tree after the commit; `close-check` must accept it before a task closes (ENG-EVID-1).
- Only the sandbox and e-agent's own containers are touched; `archive/` is read-only and existing `research/` reports stay as written, while new studies may be added under `research/` (ENG-BOUND-1, ENG-BOUND-2).
- Never flip a feature to passing without the evidence path from a successful gate.

## What runs on its own

In Claude Code, `.claude/settings.json` wires the harness in: the session starts with the `status` brief; a checkpoint is written before compaction; every `Edit`, `Write` and `NotebookEdit` is checked against the open task's scope (a closed task no longer limits unrelated edits; protected paths are always guarded); every shell command passes `bash-guard`, which denies a command that names a denied container and asks the owner when it cannot see the real command (shell `-c`, `eval`, `xargs`, `-exec`, git aliases, another docker daemon or container) or when it is `git push`, `merge`, `rebase` or `reset --hard`; with `E_AGENT_HARNESS_UNATTENDED=1` a stop is answered with `close-check`'s problems. Edits made through shell commands are not hooked, so `check-scope` before each commit stays mandatory. Codex has no hooks: run the same commands by hand.

## Start ritual

1. `uv run e-agent-harness status`: read the brief, the active task, the boundaries and the next action.
2. `uv run e-agent-harness validate-context`: must print `ok`. A problem here is fixed before anything else.
3. Confirm where you are: `git branch --show-current`, `git status --short`, `git log --oneline -5`. Work on the phase branch named in the plan, never on `main`.
4. Smoke check: `uv run e-agent-harness gate quick --package <package of the task>`.
5. One task: continue the active contract, or materialise the next unfinished feature with `uv run e-agent-harness new-task <phase> <task-id> --feature <F-id> --paths "<glob>" [--paths ...] --gate <set>`. When `status` reports a stale digest, run `uv run e-agent-harness refresh-task`; when it reports that the feature steps changed, run `refresh-task --from-features`. Both keep the base commit, creation time and scope. After a task closes, `new-task` for the next feature needs no `--replace`.
6. Commit the contract (`harness/state/**`) before the work starts, so the task's first work commit is separate.

## Work

- Research in a fresh context (the `explorer` subagent or a separate session), not in the main one; the main context holds the contract, the plan section and the files being changed.
- Follow [eng-implement](../eng-implement/SKILL.md): a failing test first, then the minimal change (ENG-WORK-2).
- `uv run e-agent-harness check-scope` before every commit; it prints `ok: N changed paths inside scope`. An out-of-scope path is a stop, not a note; when the scope itself was wrong, `uv run e-agent-harness amend-scope --add "<glob>" --reason "<why>"` records the change in the contract.
- A feature that the plan did not list (a review fix, a split task) is added with `uv run e-agent-harness add-feature <phase> <F-id> --category <part> --description "<one sentence>" --step "<check>"`; any contract file is checked with `uv run e-agent-harness validate <schema> <file>`.
- At natural breaks, and always before compacting: `uv run e-agent-harness checkpoint --session <session id> --next "<the one next step>"`.
- When the plan is wrong, rule: record what you decided, why, and the cost if wrong, in the handoff; update the plan in the same commit (ENG-PLAN-3).

## Close ritual

The order is fixed by `close-check`; evidence from a dirty tree is rejected.

1. `uv run e-agent-harness tidy` formats and lints the whole change once (Python with ruff, the UI's scoped formatter when `ui/` changed) and lists what it cannot fix; fix those, then commit the work. `check-scope` passes.
2. `uv run e-agent-harness gate <set>` with the contract's gate set, never the smoke set, on the clean tree; note the evidence path it prints (under `harness/state/evidence/`).
3. Set the task's feature entry in `harness/state/<phase>/features.json` to `"passes": true` with `"evidence": "<that path>"`.
4. Write the handoff JSON with [eng-handoff](../eng-handoff/SKILL.md); `uv run e-agent-harness handoff <task-id>` prints ok.
5. `uv run e-agent-harness checkpoint --session <session id> --next "<next task or close>"`.
6. Commit the bookkeeping (`harness/state/**` including the evidence file, `docs/handoffs/**` only).
7. `uv run e-agent-harness close-check --session <session id>` must print `ok: task may close`.
8. Review with [eng-review](../eng-review/SKILL.md) in a fresh context: the `reviewer` subagent, or Codex for trust-anchor and kernel tasks; fix findings that affect correctness or the contract; re-run steps 1 to 7 for the fix.
9. Retro line: if a correction was needed twice, add the gotcha, rule, skill line or hook in the same commit (ENG-WORK-3).
10. Clear the context. The next session's brief is `status`.

## Context strategy

| Situation | Do |
|---|---|
| Starting a new task | Clear the context; the `status` brief is the opening message |
| Long task, context filling | Checkpoint, then compact with a focus on the task id, modified files, gate results and open findings |
| Many file reads, test runs or logs | Delegate to a fresh context that returns a short summary and an evidence path |
| Two failed corrections on one issue | Rewind to before the first attempt, or clear and restate the brief with the lesson |
| Parallel tasks | One worktree per task, branched from the current phase branch, not from the default branch |
| Invariants that must survive compaction | They live in the root instruction files and this skill, never only in chat |

## Known harness limits

The Phase 1 pilot log's other rows were fixed in harness H2.1; one remains.

- A contract has one gate set (HP-6). When the plan asks for more levels per task (the Postgres run, `make e2e`), run them through [eng-verify](../eng-verify/SKILL.md) and name them in the handoff.

## Unattended variant

Allowed from roadmap Phase 2 for mechanical tasks. One worktree per task; the goal condition is the acceptance as shown by the gate command's output; `E_AGENT_HARNESS_UNATTENDED=1` so each stop is answered with `close-check`'s problems. The Stop gate is feedback, not a bound: every tool call resets Claude Code's count of consecutive Stop blocks, so set a turn cap (`--max-turns`) and a spend cap (`--max-budget-usd`), and run `close-check` yourself after the run. Results arrive as a handoff, never as a merge or a push.

## Before handing off

- [ ] `close-check` printed `ok: task may close`.
- [ ] The feature's `passes` cites the evidence path of a successful gate on a clean commit.
- [ ] The handoff lists what changed, what was verified, rulings with cost if wrong, and what remains (ENG-DOC-2).
- [ ] A fresh-context review ran and its findings that affect correctness or the contract are fixed.

## Stop gate

A task closes only on `ok: task may close`. The next task starts only in a cleared context.
