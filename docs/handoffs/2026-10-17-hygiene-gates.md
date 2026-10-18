# Hygiene: gates, typed configuration, supervised tasks and CI scans (2026-10-17)

## Summary

- **Plan:** [Hygiene plan](../plans/2026-10-15-hygiene-gates-config-ci.md), tasks H.1 to H.5; [roadmap](../roadmap.md) row 1h; [X-agent adoption review](../reviews/2026-10-14-x-agent-adoption-review.md) XA-04 and XA-14 to XA-17.
- **Branch:** `chore/hygiene-gates`, cut from local `main` at `2a6d250` after Phase 1d was fast-forwarded into it. Pushed on the owner's instruction, together with `main` (`3ae9aaf..2a6d250`). Open as [PR #4](https://github.com/thanhnc261/e-agent/pull/4), not merged.
- **Execution:** subagent-driven. For each task the harness opened a contract, one implementer subagent wrote the failing test first and then the change, and the controller ran `tidy`, the `full` gate on the clean commit, the feature flip, the task handoff and `close-check`. Reviews ran in a fresh context: Claude for H.1, H.2, H.4 and H.5, and Codex for H.3, which touches the kernel. A whole-phase Codex review followed. H.3, H.5 and the whole-phase review each asked for rework, and every finding was fixed and accepted.
- **Result:** principles PR-25, PR-31, PR-32, PR-37 and PR-38 now have machine checks and are [I]. PR-39 is [Pa] because its mechanism, a required check, needs the owner's branch protection. Run behaviour is unchanged: the OpenAPI check passes, and the CLI's stderr in the lost-response demo is empty again after the H.3 fix.

## What changed

| Commit | Content |
|---|---|
| `f2b434b` | H.1: `release_report.py` `summarize()` prints the count and fails on zero cases. ENG-EVID-4 "Gates fail on empty input" adds a finite Known silent-pass paths list |
| `3e1bde8`, `d6d2eb3` | H.2: `server/environment.py` adds `require_env` (names the variable, never its value) and `optional_env`. `profile.py` and `bootstrap.py` read the environment through them. Ruff TID251 bans `os.environ` and `os.getenv` in `src/e_agent`. ENG-ARCH-6 |
| `ce76976`, `2c5e71d` | H.3: `sdk/tasks.py` adds `supervised_task(coro, *, name, log_failure=True)`, and the worker, sweeper, heartbeat and kernel `_timed` call sites use it. `asyncio.create_task` is banned. Exemptions are six line-level `# noqa: TID251 - <reason>` comments pinned by `test_banned_api_allowlist_is_pinned`. `_timed` passes `log_failure=False`. ENG-ARCH-7 |
| `723ae97`, `c68e2aa` | H.4: golden file for the driver's `BASE_INSTRUCTIONS`, `test_base_instructions_match_golden` and `test_every_recording_is_replayed`. ENG-EVID-5 "Prompts are code" |
| `15eae16`, `a795734`, `96147dc` | H.5: a CI `security` job runs gitleaks 8.28.0 (checksum verified, full history), pip-audit 2.9.0 on the exported lock and `pnpm --dir ui audit --prod`. It runs with `bash -eo pipefail`, counts what it actually audited and fails on zero. `.gitleaks.toml` allows one fixture string at one old path. README lists the local commands |
| `bf0c1a6` | The first CI run found a pre-existing failure, also seen on `main`: `test_repo_move.py` passed locally only because of the developer's global gitignore. `repo_move._leftovers` now filters untracked caches, and the test repositories ignore the global gitignore |
| `9599a7c` | The security job is green: PR-25 is [I], the plan's boxes are ticked, and the roadmap row is Done |

Task detail, rulings and evidence: `harness/state/1h/handoffs/H.*.json`, `harness/state/1h/reviews/*.json`.

## What was verified

Final `full` gate on `625e9fc` (`harness/state/evidence/gates/H.5/2026-10-17T12-34-10.513516+00-00-full.json`), clean tree:

```text
[0] uv sync --locked                                  Checked 82 packages
[0] uv run ruff check .                               All checks passed!
[0] uv run ruff format --check .                      275 files already formatted
[0] uv run mypy                                       Success: no issues found in 123 source files
[0] uv run lint-imports                               Contracts: 12 kept, 0 broken.
[0] uv run python scripts/export_openapi.py --check
[0] uv run pytest -q                                  995 passed, 30 skipped in 51.23s
[0] pnpm --dir ui gen:check
[0] pnpm --dir ui check
[0] uv run python scripts/check_core_only.py          core-only check passed in 7.4s
```

GitHub Actions on `c24faaa`, [run 39032815905](https://github.com/thanhnc261/e-agent/actions/runs/39032815905): all five jobs green. They are lint, types, architecture and tests on py3.12 and py3.13, independent wheel install, UI layers and conformance, and secret scan and dependency audit. The first run, 39032348630, failed only `test_repo_move.py`, as `main`'s push run 39032337378 did; `bf0c1a6` fixed it.

Probes, from the task handoffs:
- **H.1:** `summarize([])` returned 0 before the fix.
- **H.2 and H.3:** Ruff probes flag each banned API in each allowed file.
- **H.3:** the CLI lost-response demo has empty stderr.
- **H.4:** a scratch recording `zz-probe.json` failed the replay check and was removed.
- **H.5:** a seeded fake `ghp_` token fails the step at both paths. Empty or marker-only requirements audit zero packages and fail. `requests==2.19.0` fails through pip-audit itself.

Local scan baseline on 2026-10-17:
- **gitleaks:** 453 to 456 commits scanned. Two raw `generic-api-key` hits at `apps/server/tests/test_pydantic_driver_e2e.py:19`, in commits `3ae9aafb` and `60a7422c`. Both are a test sentinel asserted absent from the evidence blob, not a credential, and are allowlisted for that path and that exact string only.
- **pip-audit:** 69 packages audited, 0 vulnerabilities.
- **pnpm audit:** 28 packages, 0 vulnerabilities.

Not run: no live check. The plan needs no container, and no run behaviour changed. The `odoo-live` workflow fails in 0 s on every push, as it has since 2026-10-06; it was not touched.

## Rulings

- Each task updated its own principle row; the Close step only verified them. Cost if wrong: one extra docs commit.
- H.1: the silent-pass list sits under ENG-EVID-4, because `check_agent_skills.py` rejects wrapped fields. Cost if wrong: move the list.
- H.2: Ruff selects only `TID251`, not the whole `TID` family; TID252 would add 51 unrelated findings. Cost if wrong: widen it after fixing those.
- H.3, Codex R-1: ban exemptions are line-level and pinned per banned API, not per-file, because per-file ignores are per rule code and let each allowed file skip both bans. Cost if wrong: go back to per-file ignores and accept the cross-exemption.
- H.3, Codex R-2: `_timed` passes `log_failure=False`, because its task is awaited and the caller handles the failure; otherwise CLI stderr changed. Cost if wrong: a later design for awaited child tasks replaces the flag.
- H.4: PR-32 is [I] because the replays and the golden test run in every `full` gate. The golden file covers only `BASE_INSTRUCTIONS`. Cost if wrong: back to [Pa] plus a backlog row.
- H.5: the gitleaks allowlist is one AND entry in `.gitleaks.toml`: the old path plus an anchored regex for the exact sentinel. Cost if wrong: switch to `.gitleaksignore` fingerprints.
- H.5: PR-39 stays [Pa] after the green run, because "required checks" is the owner's branch-protection setting. Cost if wrong: a one-line status flip.
- The final re-review was done by Claude because Codex stopped on its usage limit. The fix touched only CI and the plan. Cost if wrong: re-run Codex.
- The CI-only `repo_move` failure was fixed inside H.5 (scope amended), because the PR could not go green otherwise. Cost if wrong: split it into its own task.

## Deferred minors

- `actions/checkout` and `astral-sh/setup-uv` use floating major tags, as the existing jobs do, and uvx resolves pip-audit's own dependencies unpinned.
- Only `asyncio.create_task` is banned. `asyncio.ensure_future`, `loop.create_task` and `TaskGroup` are not; none of them appear under `src/e_agent`.
- A dependency that pip-audit cannot find on PyPI is skipped without failing the step when other packages were audited; the real lock has 0 skipped.
- Plan wording below the dated amendments still says "two-file allowlist" (lines 14, 47, 104 and 126).
- On zero cases, `release_report.py` writes the empty report before exiting 1.

## Open items for the owner

1. Merge PR #4.
2. Make the `security` job, and the other CI jobs, required checks under branch protection on `main`; PR-39 then becomes [I].
3. The `odoo-live` workflow fails in 0 s on every push. Its trigger or secrets need a look; it predates this phase.
4. Rotate the Odoo API keys before they expire on 2026-10-19. The integration key was exposed in this session through an editor selection.
5. Phase 2's plan is still a draft awaiting your review; it is the next phase on the roadmap.

## Changes outside the repository

| Change | Undo |
|---|---|
| `origin/main` fast-forwarded `3ae9aaf..2a6d250` and `origin/chore/hygiene-gates` created; PR #4 opened (owner's instruction) | Close PR #4 and delete the branch. Reverting `origin/main` would need a force push, which only the owner should do |
| gitleaks 8.28.0 darwin_arm64 tarball and binary in the session scratchpad. pip-audit fetched through uvx. pnpm audit queried the npm registry | Delete the scratchpad directories; nothing was installed system-wide |
