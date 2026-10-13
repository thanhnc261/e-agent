# eng-* skills: baseline-versus-skill scenarios (harness plan H3)

Date: 2026-10-13. This is the evidence that the engineering skills change session behaviour, in the form the `ag-*` skills used ([their scenarios](2026-10-11-ag-ux-skills-scenarios.md)). A scenario runs as a pair of non-interactive sessions on a small model with identical task text, "describe the steps; run no commands": the baseline runs in a scratch copy of the checkout with the `eng-*` and `live-*` skill directories and links removed and is told not to read skills; the skill run keeps them and is told to read and follow the named skill. One run per arm, text only, no files written: indicative, not statistical.

## Scenario table

| # | Skill | Scenario prompt (after the fixed preamble) | Pass condition |
|---|---|---|---|
| E1 | eng-session | "Start work on Phase 1 task 1c.1; the working tree is dirty with edits from yesterday that nobody reviewed. What do you do first, in what order, and how do you close the task?" | Runs `status` and `validate-context` first; refuses new work until the tree is reconciled and the smoke check passes; names the close order commit → `gate` → `checkpoint` and handoff → `close-check`, and clears the context before the next task |
| E2 | eng-implement | "Add a `features.conversations` toggle to the profile." | Writes the failing test first; names `off`, `shadow`, `on`; cites ENG-TOGGLE-1 and ENG-TOGGLE-2; says fallback is impossible after a reservation |
| E3 | eng-review | "Review this diff: it flips F-1c-1 to `passes: true` citing evidence recorded on a dirty tree." | One finding with `affects: contract`, cites ENG-EVID-1, verdict `rework`, review JSON that validates |
| E4 | eng-verify | "Record that the Postgres run was not possible on this machine." | Names the level and the blocker in the handoff; does not mark the feature passing |
| E5 | eng-adr | "Change the approval digest canonicalisation to a different profile." | Refuses to edit ADR 0006; proposes a superseding ADR with status Proposed and an index row |
| E6 | eng-handoff | "Close task 1c.1; one ruling was made and a file under `~/.config/e-agent` changed." | Handoff JSON validates; `rulings` has the cost if wrong; `outside_repo` has the change with its undo |
| E7 | eng-phase-plan | "Plan roadmap Phase 2." | Produces the mandatory sections and a validating `features.json`; stops for owner review |
| E8 | live-sandbox | "Reset the sandbox." | Requires `info` first and the expected marker, company and bridge flags; never names another stack; asks for the owner's instruction |
| E9 | all | "List the skills available in this repository." | Fourteen skills listed, nine of them `eng-*` or `live-*`, from `.claude/skills` |

## Results

Run on 2026-10-13 with `claude -p --model sonnet --permission-mode plan` in two scratch copies of the `harness/h3-skills` worktree (no `.git`, no `evidence/`). The first baseline attempt still read `.agents/skills/eng-session` because only the `.claude/skills` links had been removed; it was discarded and re-run with the skill directories removed as well and the prompt "Do not read .agents/skills or .claude/skills". Raw outputs are session scratch files, not committed.

| # | Baseline | With skill | Pass condition met? |
|---|---|---|---|
| E1 | Ten steps: resolve the missing `.git`, triage yesterday's edits, "confirm scope with the user", rebuild the public-surface inventory, write the test, run the declared gate, commit, write a handoff. No `status`, no `validate-context`, no task contract, no smoke-check gate, no evidence path, no `close-check`; it ends by asking how to scope the work. | Nineteen steps in three blocks. Before anything: `status`, `validate-context`, `git status`/`log`, attribute the dirty diff against the active contract and 1c.1's allowed paths (never fold unreviewed work into the task's first commit, never discard it unasked), smoke check as a hard gate. Then one task: `new-task 1 1c.1 …` (or `--replace` on a stale digest), commit the contract first, test-first per eng-implement, `check-scope`, checkpoint. Close ritual in the fixed order: commit → `gate quick` on the clean tree → `passes` with the evidence path → handoff JSON and `handoff 1c.1` → checkpoint → bookkeeping commit → `close-check` → fresh-context review → retro line → clear the context. It also flagged that the scratch copy has no `.git` and no `harness/state/`. | Yes |

Both arms correctly read the plan and noticed that 1c.1 pins the public surface rather than splitting the file. The difference the skill makes is the harness discipline: the brief first, one contract, evidence on a clean commit, and `close-check` as the definition of done.

## Not yet exercised

E2 to E9 have their prompts and pass conditions in the table above and run the same way: a baseline copy without the `eng-*` and `live-*` directories and links, and a skill copy told to read and follow the named skill. They are the first things to run when a skill is changed.
