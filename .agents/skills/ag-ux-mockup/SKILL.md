---
name: ag-ux-mockup
description: Build a comparable, verifiable agentic UI mockup from an approved brief, in a new research/mockups folder, covering every normative state with labelled samples. Stops for owner selection; never proceeds to production code.
---

# Agentic UX mockup

A mockup makes an approved brief concrete enough to judge and compare. It is a research artifact, not product code.

## Hard limits

- Requires an approved brief, made with [ag-ux-brief](../ag-ux-brief/SKILL.md). Read [ag-ux-foundations](../ag-ux-foundations/SKILL.md) first.
- Create a new folder, `research/mockups/<name>-vN/`. Never edit an earlier study. Reuse its files by importing or linking them, not by changing them.
- Use a design system only if it meets [design-system.md](../ag-ux-foundations/references/design-system.md) and the binding design-system requirements (EA-12 to EA-16). Where it falls short, fix the gap inside the new folder, or record the gap in the QA file.
- No literal colour values in components. Use semantic tokens (AG-DS-1).
- Shared geometry or token sources stay single-source: pass parameters to them rather than forking them. For example, the connected-node logo is rendered through `logoGlyphFor({...})` in the v4 `design-system/brand.js`.
- All data is fictional and labelled as a sample (EA-11). Nothing calls a model, a live system or an external network.
- Never present simulated progress, reasoning or numeric confidence (EA-5).
- The mockup does not become production code. Production work goes through [ag-ui-implement](../ag-ui-implement/SKILL.md) after owner selection.

## Workflow

1. **Plan the states.**
   - List the normative states the brief puts in scope ([state-model.md](../ag-ux-foundations/references/state-model.md)).
   - Make each one reachable, by scenario or by a labelled prototype control.
   - Include ready, working, needs input, awaiting decision, decision invalidated, rejected, executing, verifying, outcome uncertain, failed, cancelled or stopped, and verified complete, where they apply.
2. **Compose.**
   - The conversation is the primary surface, with the artifact in a closable workspace (EA-10).
   - Include mobile, tablet, desktop and embedded or docked variants.
   - When the owner is choosing between directions, make 2–3 directions that are comparable on the same scenario.
3. **Apply the decision surface rules** wherever an action is consequential: AG-APPR-1 to AG-APPR-9. Also apply truthful outcome labels (EA-3, EA-4), a reachable stop control (AG-CTRL-1), and visible AI disclosure and limits (AG-DISC-1, AG-DISC-2).
4. **Verify mechanics** with a `verify.mjs` browser script in the folder. Model it on the earlier studies' scripts. It must cover:
   - widths 320, 390, 768 and 1440 px, plus landscape;
   - light, dark and high-contrast themes;
   - keyboard-only operation of the main path and focus return;
   - no console errors and no external requests;
   - automated accessibility checks where available;
   - screenshots saved in `screenshots/`.

   Run the design system's own checks if you changed tokens.
5. **Self-review.**
   - Look at the screenshots yourself and score them with the [ag-ux-review](../ag-ux-review/SKILL.md) rubric.
   - Fix what you can. Record the rest in the QA file.
   - A passing script is not a passing design.
6. **Document** using the templates [mockup-readme.md](templates/mockup-readme.md) and [qa.md](templates/qa.md):
   - how to open the mockup;
   - what to evaluate;
   - the state map;
   - the evidence and its limits.

## Stop gate

The owner selects or approves. Do not start production implementation.
