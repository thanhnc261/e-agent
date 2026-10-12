# UI foundation adoption: results (2026-10-12)

Owner goals, in order:
- "use that logo. and finish all FE work"
- "continue to done all UI"

The logo is `e-agent-sage-lagoon-15-35-depth-1-none-shadow-glossy-multicolor.svg`, exported from the v4 identity page.

This pass adopts the paused v4 visual foundation (frontend guide §8) into the production `ui/` packages. It completes the open 2026-10-09 visual-rework package, as amended by later owner direction. Work was done in place, over the owner's uncommitted `ui/` changes, which are preserved. Nothing was committed or pushed.

## What changed

| Area | Change | Files |
|---|---|---|
| Logo | The owner's logo ships as the `BrandMark` primitive. It is used in the header, the overlay launcher and as the agent's avatar in the conversation, and is decorative beside the product name. The tinted "e" tiles are gone. The file was regenerated from v4 `brand.js` with identical parameters and spot-verified against the owner file (colours, gradients, geometry); it is not a byte-level copy of the attachment. A sha256 pins the shipped file. | `components/src/primitives/BrandMark.tsx`, `components/src/primitives/brand/e-agent-mark.svg`, `features/header/Header.tsx`, `layouts/src/overlay/OverlayLayout.tsx`, `components.css` |
| Tokens | Light theme: semantic roles repointed to the Sage Lagoon study (v4 `palette-studies.json`) over v4 Warm Lagoon neutrals. Dark and high contrast use v4's warm values. Shadows are warm-tinted. Appearance and density files are unchanged, since they hold no colour. | `tokens/tokens/{base,dark,high-contrast}.tokens.json`, regenerated `src/generated/*` |
| Theme motion | Removed `background` and `border-color` transitions from `.ea-button`. When the theme switched, text changed instantly while surfaces faded, so light text briefly sat on a light background (seen in dark-theme captures; FOUNDATION.md prohibits background-only theme animation). A new test forbids colour transitions in UI CSS. | `components/src/primitives/primitives.css`, `components/test/theme-motion.test.ts` |
| Overview (EA-10) | Conversation-first, in one 46rem column. It shows: the brand mark; the heading "What shall we move forward?"; the composer; an AI disclosure with capabilities, limits and safeguards (AG-DISC-1, AG-DISC-2); and the installed task types as a compact list under the composer. The three-column homepage catalog is removed. Strings are in EN and VI. | `apps/web/src/pages/Overview.tsx`, `apps/web/src/app/standalone.css`, `ui-core/src/i18n.ts` |
| Truthful in-flight state (gap-audit F-1) | While a run is in flight, the header names the phase from the server's action states: "Sending the change" (DISPATCHING), "Change recorded · checking" (COMMITTED) and "Change not confirmed" (UNKNOWN), with `data-phase`. Task details label all 12 action states instead of raw enums. The vanilla reference uses the same helpers. No contract change was needed. | `ui-core/src/presentation.ts` (`runStatusKey`, `actionStatusKey`), `ui-core/src/i18n.ts`, `features/header/Header.tsx`, `features/outcome/OutcomePanel.tsx`, `apps/reference-vanilla/src/main.ts` |
| Forced colours (EA-14) | Focus, selection (`aria-current`), control and surface boundaries and disabled state are restated with system colours; the brand mark keeps its colours | `components.css`, `ui-conformance/tests/forced-colors.spec.ts` |
| Polish | The evidence source disclosure is labelled "Observed values"; the recent-task status is left-aligned; the gallery documents `BrandMark` | `features/evidence/EvidencePanel.tsx`, `components.css`, `apps/gallery/src/main.tsx` |
| Tests | Added `BrandMark` tests: a sha256 pinning the shipped file, decorative use, and no shadow, glossy, multicolour. The public export inventories gain `BrandMark`, `runStatusKey` and `actionStatusKey`. Unit tests cover phase labels and the label catalog. The overview layout spec now asserts one column, which replaces the superseded three-column assertion. | `components/test/BrandMark.test.tsx`, `layouts/test/public-api.test.ts`, `ui-conformance/tests/preferences.spec.ts` |

## Rulings

- **EA-10 overrides the overview catalog.** The 2026-10-09 package asked for a three-column catalog on the overview. The owner later rejected the dashboard hierarchy (study 03 → 04, 2026-10-10), and EA-10 binds conversation first. The newer decision wins. The catalog stays reachable as a list. If wrong, restore the grid CSS and the old assertion.
- **The light accent comes from the logo's palette study.** The logo was exported from the Sage Lagoon study, so the light accent is that study's `#4a7561`. The logo colours themselves are the owner's file and are not adjusted. The logo brand `#839675` is 3.02:1 on the light canvas `#faf9f2`: decorative and above 3:1, but close. If wrong, swap the accent roles back to v4 Warm Lagoon.
- **The navigation stays as a 224px labelled sidebar,** as in the 10-09 package. It does not become v4's collapsible 68px rail, because the route conformance specs rely on the labelled section links and EA-10 does not require the rail. If wrong, the rail is a follow-up.

## Evidence

Screenshots are in `evidence/2026-10-12-ui-phase-b/` (logo and tokens only), `evidence/2026-10-12-ui-phase-c/` (overview pass) and `evidence/2026-10-12-ui-phase-d/` (final, 20 captures, all inspected; this set adds high contrast, dark and high-contrast results, forced colours and 768px): the desktop overview, session work, Connections, pending review (default, compact, presence, operator), evidence, result, dark review, compact overlay, sidebar, and mobile overview and review. The "before" set is `evidence/2026-10-09-visual-rework/pass-1/`.

Checks were run on the final tree:

| Command | Baseline (before this pass) | Final |
|---|---|---|
| `pnpm --dir ui check` | 149 tests passed; typecheck, format, boundaries, neutrality and build green | 153 tests passed; all gates green |
| `pnpm --dir ui conformance` | 138 passed, 2 skipped | 139 passed, 2 skipped (adds `forced-colors.spec.ts`) |

## UX review

[docs/reviews/2026-10-12-ui-adoption-ux-review.md](../reviews/2026-10-12-ui-adoption-ux-review.md) (ag-ux-review, review mode): approved; no open Blocker or High. Three Low findings remain open (R-1 history collapses after a resize, R-2 the compact overlay header wraps, R-3 no landscape capture). Gap-audit F-3 (Stop) was already met in production.

## Not done (blocked or out of scope)

| Item | Why |
|---|---|
| Clarification UI beyond the existing flow, proposal editing, granular feedback | No host contract (2026-10-09 package, item 5) |
| Density scale exposed as an owner-visible control on the overview | Density tokens exist (`comfortable`, `compact`) and are reachable through the preferences popover; no new control was added |
| Real assistive-technology, real-device and moderated-user evaluation | Not possible here; script checks verify mechanics only |
| Automated axe audit | No axe package in the repository |
| Forced colours on real Windows High Contrast | Emulated in Chromium only |

## Owner work preserved

A snapshot of the pre-existing uncommitted `ui/` changes was taken before editing:
- `ui-wip.patch` (6,676 lines);
- `ui-untracked.tgz` (96 files), in this session's scratch directory.

All of them remain in the working tree.
