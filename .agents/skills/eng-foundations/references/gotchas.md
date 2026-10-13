# Gotchas

Mistakes already made once in this repository. Each row names where it was seen and the rule it protects. Add a row the second time a correction is needed (ENG-WORK-3), in the same commit as the fix.

| Id | Seen | Gotcha | Rule |
|---|---|---|---|
| G-1 | Phase 1 task 1a.2 | Two test folders both importing as `tests.test_discovery` made pytest run one suite twice and the other never; keep test module basenames unique or keep each test folder a package. | ENG-WORK-2 |
| G-2 | Phase 1 task 1a.2 | A static hatch `force-include` also copies the package into site-packages for an editable install and shadows `src/`; the shared build hook in `dists/_hooks/` adds the tree only for standard wheels. | ENG-ARCH-5 |
| G-3 | Phase 1 task 1a.3 | `uv lock` cannot re-resolve when editable paths are stale; rewrite the path strings and confirm with `uv lock --check` rather than relocking, which would upgrade third-party versions. | ENG-WORK-2 |
| G-4 | Harness H2 task 3 | `git status --porcelain` lines start with a space for a modified file; stripping the output drops the first character of the path. | ENG-WORK-2 |
| G-5 | Harness H2 review | A 40-hex commit SHA can contain a short test secret such as `abc`; use a distinctive marker in redaction tests. | ENG-EVID-3 |
| G-6 | Phase 1 pilot HP-4 | Gate evidence used to live in the git-ignored `evidence/`, so references did not survive a fresh clone; since harness H2.1 it is written under `harness/state/evidence/` and committed with the bookkeeping. | ENG-EVID-1 |
| G-7 | Phase 1 pilot HP-10 | The manifest and the active plan are digest inputs; editing either mid-task makes the contract stale, and re-materialising with `--replace` is the remedy. | ENG-WORK-1 |
| G-8 | Phase 1 pilot HP-12 | `gate full` had no UI checks, and a provider identifier in a UI test stayed red on `main` unnoticed; since harness H2.1 the full gate runs `pnpm --dir ui check`. | ENG-EVID-2 |
| G-9 | Harness H2 task 3 | A gate chain piped into `tail` hides the exit code; use `set -o pipefail` or run the command last. | ENG-EVID-2 |
| G-10 | Harness H1 | A Markdown link in `CLAUDE.md` does not load `AGENTS.md` into a session; only the `@AGENTS.md` import does. | ENG-DOC-1 |
| G-11 | Phase 1 pilot HP-13 | The Postgres tests truncate their database; a test DSN that points at the live ledger wipes it. Every gate set now refuses a test DSN with the live ledger's database name on any host, and the `pg` gate requires one. | ENG-BOUND-1 |
| G-12 | Harness H2.1 | Two gate runs within one second wrote the same evidence file name; evidence names now carry the gate set and a counter. | ENG-EVID-1 |
