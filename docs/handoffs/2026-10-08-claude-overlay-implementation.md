# Claude implementation handoff: enterprise overlay

Date: 2026-10-08. The user explicitly requested that Claude implement the completed overlay adoption plan. This is an implementation assignment, not another planning exercise.

## Read first

- `AGENTS.md` and its required architecture/design documents; current README and remediation retest for actual readiness.
- `docs/plans/2026-10-08-enterprise-overlay-adoption.md` — ordered work, API dependencies and completion gates.
- `docs/frontend-development-guide.md` — folder organization, reuse, state ownership and accessibility conventions.
- `research/12-agentic-overlay-ux-research.md` and `research/14-enterprise-wide-agent-experience.md`.
- `research/mockups/agentic-overlay/` — visual and interaction reference; preserve the original study and historical prototype.

## Implement

Start with FE-00 through FE-04: baseline checks, scoped formatting, behavior-preserving module extraction, reusable primitives/tokens, the shared task surface and its four placements, and neutral Overview/session-work navigation. Keep the existing package architecture, public exports, slot contracts, controller lifetime and approval/evidence authority intact.

Continue through the remaining planned increments: FE-05 appearance variants when they meet the gates, API-01 authorized member discovery contracts and FE-06 catalog/Connections, then FE-07 qualification and handoff. Establish the required ADR and update affected designs before material contract changes. The user has authorized implementation of this plan; do not ask again about routine implementation choices or stop merely because planning documents are marked proposed. Record any truly unresolved scope decision explicitly and continue independent work.

Make the product enterprise-wide in structure and language. Show only supported, authorized capabilities. Extra provider integrations, durable cross-session inboxes, proposal editing, OAuth administration and cross-origin authentication are not supplied by the mockup; retain the plan's boundaries. Do not replace working backend authority with prototype simulation or expose dummy connections in production.

## Working-tree and execution constraints

The checkout contains extensive existing tracked and untracked changes, including the actual UI implementation and this plan. Inspect and preserve them. Do not reset, clean, discard, overwrite or commit unrelated work. Work in this checkout so the uncommitted baseline remains available; do not create a clean worktree that silently omits it. Do not commit, push or deploy unless separately requested.

Run no live business mutations, model/provider qualification or sandbox resets for this UI assignment. Do not touch the separate `enterprise-agent/experiment` research system. Use existing deterministic fixtures for local verification. Preserve unknown external outcomes, explicit per-action approval, stale-approval rejection and independent verification semantics.

Use normal tool permission checks. If a tool is denied or an environmental prerequisite is unavailable, report the precise blocker; do not bypass protections or claim the step passed.

## Verification and delivery

Run the appropriate repository checks, including `pnpm --dir ui check` and `pnpm --dir ui conformance`, plus meaningful backend/contract checks when API-01 changes them. Check generated contract/token diffs carefully against the dirty baseline. Add focused tests for changed behavior, review actual desktop/mobile/embedded renders, and exercise keyboard, focus, EN/VI, theme and approval states.

Keep progress visible and implement coherent increments. Update README and relevant implementation notes to reflect only completed work. Write the final report to `docs/handoffs/2026-10-08-enterprise-overlay-implementation-results.md`, listing work-package status, changed behavior, actual verification results, screenshot/evidence paths, failures/skips and remaining unimplemented work. Fixture success must not change the current live-release readiness claim.
