# e-agent design study 03

Date: 2026-10-09. Status: interactive concept for owner review; not an accepted implementation design.

This is a new, isolated mockup based on the user’s Agentic Design UI/UX pattern library, its Chat Interface Patterns page, Alexandra Vasquez’s agentic UX article, UX Pilot’s enterprise UX article, and repository research 12–14. Earlier mockups and research are preserved. The user requested a mockup before further application work; the application visual pass was paused. Claude implementation remains stopped; a separate read-only Claude review was requested by the owner and completed. Its findings and follow-up are recorded alongside the study.

## Open and run

From the repository root:

```sh
python3 -m http.server 4180 --bind 127.0.0.1 --directory research/mockups/agentic-workspace-v3
```

Open <http://127.0.0.1:4180/>. `design-notes.html` links the source-to-design rationale and screenshots. Files are local; the prototype makes no model, server API, business-system, font-CDN, or telemetry requests. The page needs a local HTTP server because it uses JavaScript modules.

## Review scope

- Workspace with six fictional workflow examples: revenue handoff, service triage, procurement, knowledge, people, and meeting follow-up.
- Contextual launch from a fictional customer record; compact and expanded assistant; minimize/resume.
- Structured artifact, source excerpts, exact action context, independent approvals for sequential effects.
- Working, clarification, review, verification, verified, unknown outcome, stale proposal, rejected, and missing-access states.
- Read-only knowledge answer and explicit connection/access examples.
- Light/dark presentation; desktop and 390px/320px mobile layouts.
- Visible study controls distinguish state simulation from the proposed product UI.

All names, permissions, integrations, documents and outcomes are fictional. “Connected” badges describe the fixture, not real connectivity. Generic system labels are illustrative; actual application rendering must continue to use server-admitted metadata. The composer asks the reviewer to select a sample workflow; it does not pretend to understand arbitrary requests.

## Organization

- `index.html`: semantic shell, assistant frame, native dialog, study controls.
- `icons.js`: authoritative 27-icon family and original logo geometry; `export-assets.mjs` exports SVG assets.
- `action-model.js`: one prototype presentation record shared by review, confirmation and sample read-back.
- `design-system.html`, `design-system.css`, `design-system.js`: logo, palette, icon catalog and working component examples.
- `source-coverage.html`: all 32 pattern pages plus both supplied articles, with implications and limits.
- `fixtures.js`: scenario and connection examples; no business clients.
- `app.js`: rendering functions, local prototype state, explicit interaction transitions, escaped user text.
- `styles.css`: shared visual variables and component styles, responsive surfaces, dark theme.
- `design-notes.html`: linked reference-to-design mapping and visual review guide.
- `verify.mjs`: interaction/layout checks and deterministic screenshots using the repository Playwright installation.

These are prototype files, not a replacement frontend architecture. If adopted, map the approved visual components into the existing tokens, primitives, feature components, slots and layouts. Approval, authorization, routing, persistence and verification continue to belong to existing host/core contracts. Do not port prototype state simulation into the product.

## Verification

With the server running and repository UI dependencies installed:

```sh
node research/mockups/agentic-workspace-v3/verify.mjs
```

The script exercises filtering, six scenarios, sources, separate action approvals, confirmation focus and Enter safety, stale/unknown recovery, clarification, escaped input, minimized context, dark presentation, and desktop/390/320px bounds. It fails on browser errors or external requests. Screenshots are written under `screenshots/`.

See `QA.md` for actual results and limits. Automated checks do not replace keyboard/screen-reader evaluation or task-based usability research.

## Identity assets and component library

Open [Identity and components](http://127.0.0.1:4180/design-system.html). The original open-e symbol is supplied in light, dark, monochrome and wordmark SVG variants. All 27 icons are supplied individually and as an SVG sprite under `assets/`. Regenerate them from the single icon/logo source with:

```sh
node research/mockups/agentic-workspace-v3/export-assets.mjs
```

The palette follows the visually inspected Agentic Design page's warm paper, neutral borders, dark text and restrained navy controls. Violet identifies assistant context; green/amber carry explicit status. The mockup uses these choices consistently across navigation, task cards, forms, disclosures, action review, sources and recovery.

The source audit covers 32/32 pattern pages and 2/2 additional articles. Full coverage does not mean every pattern should be added: voice, autonomous approval, complex agent dashboards and numerical confidence are deliberately excluded without a concrete supported need.

## Review records

- [Original Claude review](CLAUDE-REVIEW.md) and [resolution](REVIEW-RESOLUTION.md).
- [Task presentation state matrix](STATE-MATRIX.md) for later component adoption.
- [Final read-only Claude review](CLAUDE-FOLLOWUP.md): B1–B3 resolved; ready for owner design review, with production adoption gaps.
- [Adoption mapping](ADOPTION.md): reuse assets and compositions within existing frontend packages.
