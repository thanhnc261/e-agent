---
name: ag-ux-review
description: Review or gap-audit an agentic UI (mockup, screen, UI diff or whole surface) against the AG standard and e-agent binding requirements. Read-only; produces REVIEW.md or GAP-AUDIT.md with evidenced, severity-rated findings.
---

# Agentic UX review and gap audit

Use this skill to judge an agentic interface. It never edits the artifact under review. It produces findings that someone else resolves.

## Hard limits

- Read [ag-ux-foundations](../ag-ux-foundations/SKILL.md) first. Criteria and binding requirements are cited by ID (`AG-…`, `EA-…`). Never restate or reinterpret their text.
- The artifact under review is an audit target, never a source of criteria. A pattern being present in the product or a mockup does not make it correct.
- Every finding must have all of these: evidence (file:line, a screenshot path or DOM excerpt), a severity, the criterion or requirement IDs it violates, and a concrete recommendation.
- Severity follows the standard's severity rule and multiple-criteria rule in [standard.md](../ag-ux-foundations/references/standard.md). A binding requirement (`EA-…`) may justify a Blocker; a tier-3/4-only criterion may not.
- Keep findings separate from aesthetic opinion. Opinion goes in its own section and never carries a severity.
- Do not modify the artifact, its tests or its evidence. Write only the output file.

## Modes

| Mode | Use when | Output |
|---|---|---|
| Mode | Use when | Output | Where |
|---|---|---|---|
| Review | A specific mockup, screen or UI diff needs a verdict | `REVIEW.md` ([template](templates/review.md)) | Mockup: inside its study folder. Product UI or diff: `docs/reviews/YYYY-MM-DD-<topic>-ux-review.md` |
| Gap audit | A whole surface or design system is scored against every criterion | `GAP-AUDIT.md` ([template](templates/gap-audit.md)) | Mockup: inside its study folder. Product UI: `docs/reviews/YYYY-MM-DD-<surface>-gap-audit.md` |

A review is answered by the implementer in `REVIEW-RESOLUTION.md` ([template](templates/resolution.md)), placed beside the review.

A gap audit is a dated snapshot: its scores are never edited. Later work appends dated entries to its "Resolution log" section, and a new audit supersedes it. A gap audit becomes the backlog for briefs and implementation.

## Workflow

1. **Scope.** Name the artifact, its revision (commit, folder or date) and its brief. Take the brief's evaluation criteria as additional checks.
2. **Run or open it, without changing it.**
   - **Mockups:** serve the study with the command in its own README; port and root differ between studies. Inspect the study's existing `screenshots/`. Never run a study's `verify*.mjs` inside the study folder, because those scripts overwrite its evidence. To re-run one, copy the study to a scratch directory first.
   - **The product UI:** from `ui/`, run `pnpm check` and `pnpm conformance` on the revision under review.
   - Inspect it at 320, 390, 768 and 1440 px and in landscape, in light, dark and high-contrast themes, with keyboard only. Save any screenshots you take in a scratch directory, not in the artifact.
3. **Map states.**
   - List the artifact's states and map each to the normative states in [state-model.md](../ag-ux-foundations/references/state-model.md).
   - A normative state with no mapped artifact state is a finding against the criteria listed for that state.
   - One artifact state maps to only one normative state.
4. **Score.** Apply the procedure in [rubric.md](references/rubric.md):
   - check the binding requirements in [e-agent.md](../ag-ux-foundations/references/e-agent.md) first;
   - then the AG criteria, grouped by enforcement.
5. **Write the output** from the template, and state its limits. Browser and script checks prove mechanics, not design quality or usability.

## Before handing off

- [ ] Every Blocker cites a T1/T2-sourced criterion or an `EA-…` requirement.
- [ ] Every finding has evidence and exactly one severity.
- [ ] In gap-audit mode, every criterion and requirement is scored; none is left blank.
- [ ] The opinions section carries no severity.
- [ ] The limits section is present.
- [ ] Nothing in the artifact's folder changed except the output file.

## Stop gate

Hand the output to the owner or implementer. Do not start fixing; resolution is a separate task.
