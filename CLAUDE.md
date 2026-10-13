# Claude project guidance

@AGENTS.md

AGENTS.md above is the shared instruction source for conventions, architecture boundaries, safety invariants and verification; this file adds only what is specific to Claude Code. Do not duplicate the shared rules here or maintain a second architecture specification. Current user instructions take precedence over repository guidance. For the current state, read the [roadmap](docs/roadmap.md) and the README status; inspect the actual checkout and report implementation versus proposal accurately.

- **Plans and specs.** Write plans to `docs/plans/` and specs to `docs/specs/`. This overrides the superpowers skills' default `docs/superpowers/` location.
- **Execution.** Execute a plan task by task with subagent-driven development; its ledger lives in the git-ignored `.superpowers/sdd/`. Research the repository through subagents; keep the main context for the task contract, the plan section and the files being changed.
- **Harness.** Start from `uv run e-agent-harness status` and follow its single next action. Run `check-scope` before each commit and `close-check` before a task closes.
- **UI.** Use the `ag-*` skills for any UI/UX work (AGENTS.md, "UI/UX skills").
- **Decisions.** Consult the advisor before committing to an approach and before declaring a task done.
- **Commits.** Stage explicit paths. End every commit message with the `Co-Authored-By` trailer from the session's attribution instructions. Never merge, push or rebase shared branches without the owner.

# Compact instructions

When compacting, keep: the active task contract id and its file path; the full list of modified files; the gate commands run and their last result; open review findings; and the single next action.
