---
name: ag-ux-foundations
description: Agentic enterprise UI/UX standard (AG-* criteria, state model, patterns, design-system and frontend rules). Read before any agentic UI brief, mockup, implementation or review; cite criteria by ID.
---

# Agentic UI/UX foundations

This is the standard that agentic UI/UX work is built and reviewed against. It is product-neutral; a product's binding requirements live in one separate reference.

## Authority

- The standard defines what good looks like. A product's current implementation is an audit target, never a source of criteria.
- A product's binding requirements (accepted architecture decisions, repository rules, owner decisions) cannot be weakened. Where the standard conflicts with one, propose a decision change; do not override it.
- Where the standard is stricter than the implementation, record a gap and build to the standard.
- Cite criteria by ID (`AG-…`). Do not copy criterion text into other documents.

## Reading order

1. [standard.md](references/standard.md): interaction criteria.
2. [state-model.md](references/state-model.md): the normative task states.
3. [e-agent.md](references/e-agent.md): binding requirements for this repository.
4. As the task needs: [patterns.md](references/patterns.md), [design-system.md](references/design-system.md), [frontend.md](references/frontend.md), [metrics.md](references/metrics.md), [sources.md](references/sources.md).

## Rules for every use

- A Blocker finding must rest on a T1 or T2 source, or a binding requirement.
- Never present model chain-of-thought, simulated progress or uncalibrated confidence.
- Never claim success before independent verification.
- Read a new source at its origin and record its reading level in `sources.md` before citing it.
- Browser checks prove mechanics, not design quality or usability; say so in every report.

## Changing the standard

Add or edit criteria only with sources read at `full` or `partial`, keep IDs stable (retire, never renumber), update `sources.md`, and run the repository's skill check. Durable-rule changes need owner approval.
