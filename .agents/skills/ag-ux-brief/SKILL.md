---
name: ag-ux-brief
description: Turn an agentic UI/UX request into an approved design brief (roles, normative states, applicable AG criteria and EA requirements, sources, 2-3 directions, evaluation criteria). Use before any agentic mockup; stops for owner approval.
---

# Agentic UX brief

A brief fixes what is being designed and how it will be judged, before anyone draws it. It is the gate in front of [ag-ux-mockup](../ag-ux-mockup/SKILL.md).

## Hard limits

- Read [ag-ux-foundations](../ag-ux-foundations/SKILL.md) first. Cite criteria (`AG-…`) and binding requirements (`EA-…`) by ID; never restate them.
- Keep the owner's words separate from your assumptions. Never present an assumption as a requirement.
- The current product or an earlier mockup is evidence of the current state, not a requirement. Reuse it only after checking it against the standard. Where a gap audit exists, cite its findings.
- Read any new source at its origin. Record the reading level in the foundations `sources.md` before you cite it.
- Do not design screens, write code or choose a final direction in the brief.

## Workflow

1. **Record the request** verbatim, with its date and who asked.
2. **Separate statements from assumptions** in a two-column table, and invite correction.
3. **Read context.** Relevant repository docs and research, plus the latest gap audit if there is one. Say what this brief extends or supersedes. Cite untracked files as plain paths.
4. **Name roles and states.**
   - Roles: requester, approver, operator or steward, as they apply.
   - The affected normative states from [state-model.md](../ag-ux-foundations/references/state-model.md), with the user need for each.
5. **Select criteria.**
   - List the AG criteria and EA requirements the design must satisfy, grouped by state.
   - Mark the ones the current state fails, citing gap-audit finding numbers where available.
   - Choose the patterns from [patterns.md](../ag-ux-foundations/references/patterns.md) by name, with the decision they carry (apply, limit or exclude).
6. **Propose 2–3 directions.** Each direction gets a name, a one-paragraph description, its trade-offs, and the criteria it makes easier or harder. Recommend one, with a reason.
7. **Define evaluation.**
   - Pick metrics from [metrics.md](../ag-ux-foundations/references/metrics.md), and say how each would be measured.
   - Say what a browser check will verify (mechanics only).
8. **List open questions** that only the owner can answer.

Write the result as `research/NN-<topic>.md` with status "candidate", using the [template](templates/brief.md). NN is the next free research number. Check `research/README.md` and every file in `research/`, including uncommitted ones in the owner's main checkout. `git worktree list` shows that checkout's path. A clean worktree may lack the newest studies.

## Before handing off

- [ ] The request is quoted verbatim, and every assumption is marked as an assumption.
- [ ] Every in-scope normative state has a user need and its criteria, cited by ID and not restated.
- [ ] Every current-state claim cites evidence: a gap-audit finding, file:line, or "no audit yet".
- [ ] There are 2–3 directions with trade-offs, and one recommendation.
- [ ] The evaluation separates metrics (people) from browser checks (mechanics).
- [ ] Open questions are listed. The Approval section reads "pending" unless the owner has approved.

## Stop gate

The owner approves the brief. Approval must name this brief, or the specific design it covers, and the chosen direction. A general instruction to keep working is not approval. Record the approval verbatim in the Approval section.
