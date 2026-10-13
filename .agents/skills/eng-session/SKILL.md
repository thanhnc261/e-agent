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
- Only the sandbox and e-agent's own containers are touched; `archive/` and `research/` are read-only (ENG-BOUND-1, ENG-BOUND-2).
- Never flip a feature to passing without the evidence path from a successful gate.

## Start ritual

1. `uv run e-agent-harness status`: read the brief, the active task, the boundaries and the next action.
2. `uv run e-agent-harness validate-context`: must print `ok`. A problem here is fixed before anything else.
3. Confirm where you are: `git branch --show-current`, `git status --short`, `git log --oneline -5`. Work on the phase branch named in the plan, never on `main`.
4. Smoke check: `uv run e-agent-harness gate quick --package <package of the task>`.
5. One task: continue the active contract, or materialise the next unfinished feature with `uv run e-agent-harness new-task <phase> <task-id> --feature <F-id> --paths "<glob>" [--paths ...] --gate <set>`. When `status` reports a stale digest, re-run `new-task` with the same arguments and `--replace` (the base commit and creation time are kept).
6. Commit the contract (`harness/state/**`) before the work starts, so the task's first work commit is separate.

## Work

- Research in a fresh context (a delegated agent or a separate session), not in the main one; the main context holds the contract, the plan section and the files being changed.
- Follow [eng-implement](../eng-implement/SKILL.md): a failing test first, then the minimal change (ENG-WORK-2).
- `uv run e-agent-harness check-scope` before every commit; an out-of-scope path is a stop, not a note.
- At natural breaks, and always before compacting: `uv run e-agent-harness checkpoint --session <session id> --next "<the one next step>"`.
- When the plan is wrong, rule: record what you decided, why, and the cost if wrong, in the handoff; update the plan in the same commit (ENG-PLAN-3).

## Close ritual

The order is fixed by `close-check`; evidence from a dirty tree is rejected.

1. Commit the work. `check-scope` passes.
2. `uv run e-agent-harness gate <set>` on the clean tree; note the evidence path it prints.
3. Set the task's feature entry in `harness/state/<phase>/features.json` to `"passes": true` with `"evidence": "<that path>"`.
4. Write the handoff JSON with [eng-handoff](../eng-handoff/SKILL.md); `uv run e-agent-harness handoff <task-id>` prints ok.
5. `uv run e-agent-harness checkpoint --session <session id> --next "<next task or close>"`.
6. Commit the bookkeeping (`harness/state/**`, `docs/handoffs/**` only).
7. `uv run e-agent-harness close-check --session <session id>` must print `ok: task may close`.
8. Review with [eng-review](../eng-review/SKILL.md) in a fresh context; fix findings that affect correctness or the contract; re-run steps 1 to 7 for the fix.
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

Workarounds until the harness fixes land; the ids refer to the Phase 1 pilot log.

- After `close-check` passes, `status` still shows the close action and `new-task` for the next task needs `--replace` (HP-3, HP-9).
- Editing the active plan or the manifest mid-task makes the contract stale; re-materialise with `--replace` (HP-10).
- Widening scope needs `new-task --replace` with the full path list; record the reason in the handoff (HP-11).
- `gate full` has no UI unit tests; a change under `ui/**` also runs `pnpm --dir ui test` by hand (HP-12).
- Evidence under `evidence/` is local only; copy the key numbers into the handoff (HP-4).
- Right after `new-task`, `status` asks for a commit although only bookkeeping is dirty; commit the contract and continue (HP-2).

## Unattended variant

Allowed from roadmap Phase 2 for mechanical tasks. One worktree per task; the goal condition is the acceptance as shown by the gate command's output, with a turn cap; a spend budget; `E_AGENT_HARNESS_UNATTENDED=1` so `close-check` gates the stop. Results arrive as a handoff, never as a merge or a push.

## Before handing off

- [ ] `close-check` printed `ok: task may close`.
- [ ] The feature's `passes` cites the evidence path of a successful gate on a clean commit.
- [ ] The handoff lists what changed, what was verified, rulings with cost if wrong, and what remains (ENG-DOC-2).
- [ ] A fresh-context review ran and its findings that affect correctness or the contract are fixed.

## Stop gate

A task closes only on `ok: task may close`. The next task starts only in a cleared context.
