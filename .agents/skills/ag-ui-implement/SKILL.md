---
name: ag-ui-implement
description: Implement an approved agentic UI design in e-agent's ui/ packages to the AG standard, with tests-first, server-owned state, conformance tests per touched criterion and real check output. Use for any ui/ change with UX impact.
---

# Agentic UI implementation

This skill turns a selected mockup, or an in-scope design, into production UI code under `ui/`.

## Hard limits

- Requires an owner-selected mockup (from [ag-ux-mockup](../ag-ux-mockup/SKILL.md)) or a change inside an already approved design.
- A change to an API contract, approval presentation, run-event stream or layer boundary needs an accepted decision record (ADR) first. Stop and propose one.
- Read [ag-ux-foundations](../ag-ux-foundations/SKILL.md) first. Build to the AG criteria and the binding requirements EA-1 to EA-16. On conflict, binding requirements win, and [frontend.md](../ag-ux-foundations/references/frontend.md) (AG-FE) wins over any other guide.
- The repository's frontend guide (`docs/frontend-development-guide.md`) describes the intended layering. Its folder tree is illustrative: inspect the actual tree, and never assume example names. Treat its section on the default visual foundation as paused, not as a spec to implement.
- The server is authoritative (EA-1, AG-FE-1, AG-FE-12). Every name, explanation, progress milestone and outcome comes from server data through `ui-core` selectors. When data is missing, show the limitation (AG-UNC-4, EA-8); never invent it.
- Never copy mockup prototype code, fixture state or scenario logic into production packages.

## Workflow

1. **Locate the work.**
   - Read [ui-architecture.md](../../../docs/ui-architecture.md) and the actual `ui/packages/*/src` tree.
   - Name the layer that owns each change: tokens, primitive, feature view or container, slot, layout or host.
   - Each piece of state has one owner (AG-FE-2).
2. **Map criteria to tests.**
   - For every AG criterion or EA requirement the change touches, decide its check:
     - `gate` or `test` criteria get an automated test (a unit test in the package's `test/` folder, or a browser test in `ui-conformance`);
     - `review` criteria get a note for the reviewer.
   - Write the failing tests first.
3. **Implement.**
   - Mutually exclusive states are one discriminated union (AG-FE-4).
   - Unknown wire shapes produce an explicit unsupported state (AG-FE-13).
   - Interactive primitives follow APG patterns (AG-FE-5, AG-A11Y-2).
   - Layout responds to container width (AG-FE-6).
   - Embedded focus stays inside the boundary (AG-FE-7).
   - Use only semantic tokens (AG-DS-1).
   - New CSS or DOM features follow the Baseline rule (AG-FE-8).
   - No sensitive data goes into URLs, storage or telemetry (AG-FE-10).
4. **Verify.** From `ui/`, run:
   - `pnpm check` (typecheck, format, unit tests, layer boundaries, provider neutrality, build);
   - `pnpm conformance` (browser contract suite).

   Report the real output, including failures and skips. Never report counts from earlier runs.
5. **Review.** Run [ag-ux-review](../ag-ux-review/SKILL.md) in review mode on the diff and the running UI. Resolve the findings, or record them in `REVIEW-RESOLUTION.md`.
6. **Close the loop.**
   - Update the matching gap-audit entries.
   - If layer ownership or a public contract changed, update `docs/ui-architecture.md` in the same change.

## Done means

All of these hold:
- the tests for the touched criteria exist and pass;
- `pnpm check` and `pnpm conformance` pass;
- the review has no open Blocker or High;
- the limits are stated (no real assistive-technology, device or user testing, unless it was done).
