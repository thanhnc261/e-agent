---
name: eng-adr
description: Write or supersede an architecture decision record and update the ADR index.
---

# Engineering ADR

One decision per record. A Proposed ADR changes nothing until the owner accepts it; an accepted ADR's decision is never edited, only superseded.

## Hard limits

- Read [eng-foundations](../eng-foundations/SKILL.md) first; cite rules by ID.
- A contract or boundary change needs an ADR before the phase merges, and Proposed is not baseline (ENG-PLAN-2).
- Never edit the Decision section of an accepted ADR. Write a new ADR that supersedes it and mark the old one `Superseded by NNNN`.
- When an ADR is accepted, update the affected design sections in the same change (ENG-PLAN-3, ENG-DOC-1).

## Workflow

1. **Number:** the next free number in `docs/adr/README.md`.
2. **Write** `docs/adr/NNNN-<slug>.md` from [adr.md](templates/adr.md): title line `# ADR NNNN: <title>`; a status line `Date: <YYYY-MM-DD>. Status: Proposed. Refines <ADRs> / Supersedes <ADR>; <design section>.`; then Context, Decision, Alternatives considered, Consequences, Gates.
3. **Index:** add a row to the table in `docs/adr/README.md` with four cells: the number linked to the new file, the title, `Proposed`, and the gate or phase that implements it.
4. **Link** the ADR from the phase plan's ADRs section and, when it refines a design section, from that section.
5. **On acceptance:** change the status line to `Status: Accepted (<date>, owner)`, update the index row, and update the design sections the ADR names in the same change.

## Before handing off

- [ ] One decision, stated in the Decision section as bullet points a reviewer can check.
- [ ] Alternatives name why each was rejected.
- [ ] Consequences list what changes for code, tests, evidence and operations.
- [ ] Index row present; status Proposed until the owner accepts.

## Stop gate

The owner accepts the ADR by name. Record the acceptance in the status line; until then the change it describes does not merge.
