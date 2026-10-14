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

In Claude Code, `.claude/settings.json` wires the harness in: the session starts with the `status` brief; a checkpoint is written before compaction; every `Edit`, `Write` and `NotebookEdit` is checked against the open task's scope (a closed task no longer limits unrelated edits; protected paths are always guarded; the checkout that holds the file decides, and a file outside every harness checkout, such as the scratchpad or Claude's memory, is refused only when it matches a manifest `denied_paths` glob); every shell command passes `bash-guard`, which denies a command that names a denied container and asks the owner when it cannot see the real command (shell `-c`, `eval`, `xargs`, `-exec`, git aliases, another docker daemon or container) or when it is `git push`, `pull`, `merge`, `rebase` or a `reset` that can discard work (the full list is in "What bash-guard passes" below); with `E_AGENT_HARNESS_UNATTENDED=1` a stop is answered with `close-check`'s problems. Edits made through shell commands are not hooked, so `check-scope` before each commit stays mandatory. Codex has no hooks: run the same commands by hand.

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

## What bash-guard passes, and what it is not

`bash-guard`'s contract is the short list of git and docker commands that pass without a prompt; every other command that runs git or a container tool asks, and one that names a denied container is denied. Silent pass needs a command it parses completely:

- **git:** a subcommand on bash-guard's list (not `difftool`, `mergetool` or `maintenance`) other than `push`, `pull`, `merge`, `rebase`, `reset` with an option outside `--soft`, `--mixed`, `--quiet` and `--patch`, `submodule foreach`, and `bisect` other than `start`, `good`, `bad`, `new`, `old`, `skip`, `reset`, `log` and `terms`; every `git` word in the command is checked, not only the first; no alias; no `-c`, `--config-env` or `--exec-path`; no option that runs another program (`--upload-pack`, `clone -u`, `archive --exec`, `grep -O`, `--ext-diff`); `config` only to read.
- **docker** (podman always asks): `ps`, `ls`, `images`, `version`, `info`; `exec`, `logs`, `inspect`, `top`, `port`, `stop`, `start`, `restart`, `kill`, `rm`, `pause`, `unpause` and `wait` on allowed container names with known options, where `exec` runs neither git, a container tool nor a shell `-c`; `compose -p <allowed project>` with `ps`, `logs`, `top`, `images`, `ls`, `version` or `config`. Compose `stop`, `start`, `restart`, `pause` and `unpause` ask, because compose acts on the project's existing containers, whose names are not in the command.
- **Environment:** no variable assignment or `export` anywhere in a command that runs git or docker, no inherited docker endpoint, context, config, `HOME` or `COMPOSE_` variable, not under `sudo` or another user, and a persisted docker context on a local socket.

To stay on the silent list: write a commit message with `git commit -F - <<'EOT'` rather than `"$(cat <<'EOT' …)"` (a substitution next to git asks); use `git --no-pager` rather than `GIT_PAGER=cat` (an assignment next to git asks); redirections such as `2>&1` and `> file` are fine. It is not a sandbox. It does not inspect scripts or programs the command runs (`./deploy.sh`, `python -c`), the files and configuration they read, or deliberate obfuscation. The guarding hook commands end in `|| exit 2` and the wrapper denies after its own 45 s timeout, so a startup failure or a stalled check denies even on Claude Code releases that ignore `onFailure`. Treat bash-guard as one layer: the permission rules are another, and an unattended run needs a real boundary too: Claude Code's sandbox (filesystem and network isolation) or a container without the Docker socket and without push credentials, with branch protection on the remote as the last line for pushes.

## Unattended variant

Allowed from roadmap Phase 2 for mechanical tasks. One worktree per task; the goal condition is the acceptance as shown by the gate command's output; `E_AGENT_HARNESS_UNATTENDED=1` so each stop is answered with `close-check`'s problems. The Stop gate is feedback, not a bound: every tool call resets Claude Code's count of consecutive Stop blocks, so set a turn cap (`--max-turns`) and a spend cap (`--max-budget-usd`), and run `close-check` yourself after the run. Results arrive as a handoff, never as a merge or a push.

## Before handing off

- [ ] `close-check` printed `ok: task may close`.
- [ ] The feature's `passes` cites the evidence path of a successful gate on a clean commit.
- [ ] The handoff lists what changed, what was verified, rulings with cost if wrong, and what remains (ENG-DOC-2).
- [ ] A fresh-context review ran and its findings that affect correctness or the contract are fixed.

## Stop gate

A task closes only on `ok: task may close`. The next task starts only in a cleared context.
