# Review resolution: production UI after the v4 foundation adoption

- **Review:** [2026-10-12-ui-adoption-ux-review.md](2026-10-12-ui-adoption-ux-review.md)
- **Resolved by:** Claude, 2026-10-12
- **Revision:** `ui/` working tree on `main` at `af50c62`, plus the uncommitted adoption changes (nothing committed)

The defects that were fixed during the review pass are listed in the review's "Resolved in this pass" table. The findings below are the ones the review left open.

| Finding | Resolution | Evidence |
|---|---|---|
| R-1: Recent tasks collapse after a resize | Not fixed. Deferred to the owner: the behaviour lives in owner-WIP `TaskNavigation.tsx`, and the final capture run did not reproduce it (history open in `evidence/2026-10-12-ui-phase-d/desktop-result*.png`), so it depends on timing. | `ui/packages/components/src/features/task-navigation/TaskNavigation.tsx:13` |
| R-2: Compact overlay header wraps | Not fixed. Deferred: moving the view switch is a layout decision for the next slice. | `evidence/2026-10-12-ui-phase-d/mobile-overlay-approval.png` |
| R-3: No landscape capture | Not fixed. Deferred: it is a coverage gap, not a defect. | `ui/packages/ui-conformance/tests/visual-review.spec.ts` |

## Checks re-run

| Command | Result |
|---|---|
| `pnpm --dir ui check` | Pass: 153 tests, all gates green |
| `pnpm --dir ui conformance` | 139 passed, 2 skipped |
| `E_AGENT_UI_CAPTURE_DIR=… playwright test visual-review` | 20 captures in `evidence/2026-10-12-ui-phase-d/`, all inspected |

## Open items for the owner

- Decide whether R-1 and R-2 go into the next slice.
- The navigation-rail ruling: the labelled 224px sidebar was kept instead of v4's 68px rail. It is recorded in the results handoff.
