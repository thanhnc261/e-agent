# ADR 0009: rule inventory declares an enforcement engine per rule

Date: 2026-10-06. Status: Accepted (project owner, decisions D1–D5, 2026-10-06).

## Context

The design requires one authoritative rule inventory with SHACL as the validation engine. Not every procurement rule is a shape constraint:

- PR-002 (`quantity = max(demand − available, 0)`) and PR-004 (`subtotal ≤ budget`) are arithmetic over several nodes. SHACL Core cannot express them; SHACL-SPARQL can, or the normalizer can materialize derived facts that Core shapes then check.
- PR-006 (tenant/company scope) is authorization, decided by policy, not by a shape.
- Some acceptance checks belong to the post-commit verifier, not pre-dispatch validation.

SHACL 1.2 Core and SPARQL are still W3C Working Drafts in 2026. SHACL 1.1 (2017) is the Recommendation. pySHACL supports SHACL Core, SHACL-SPARQL and SHACL-AF.

## Decision

1. The rule inventory (a packaged resource in the domain pack) has one entry per rule: `id`, `version`, `bounded_context`, `description`, `engine` ∈ {`shacl-core`, `shacl-sparql`, `normalizer-derived`, `policy`, `verifier`}, `asset` (shape IRI, policy rule ID or verifier check ID), `severity`, and positive, negative and missing-data fixture IDs.
2. `normalizer-derived` rules may compute derived facts only with a declared formula in the inventory. The derived value is then checked by a shape. The formula and its fixture are versioned with the rule.
3. Baseline engine: **SHACL 1.1 + SHACL-SPARQL via pySHACL**, pinned. No SHACL 1.2-only features until 1.2 is a Recommendation and the engine supports it.
4. Initial assignment:

| Rule | Engine |
|---|---|
| PR-001 references resolve in scope | `shacl-core` (presence/class) + `policy` (scope) |
| PR-002 shortage quantity | `normalizer-derived` (shortage) + `shacl-core` (`sh:equals`/value check) |
| PR-003 approved offer | `shacl-core` |
| PR-004 positive qty, unit/currency, budget | `shacl-core` + `shacl-sparql` (budget) |
| PR-005 delivery date bound | `shacl-sparql` (date comparison) |
| PR-006 tenant/company scope | `policy` |

5. A CI check confirms that every inventory entry resolves to an existing asset, every asset is referenced by exactly one entry, and every rule has its three fixture classes.

## Alternatives considered

- **Pure SHACL Core.** It cannot express PR-002, PR-004 and PR-005 cleanly.
- **Python validators for arithmetic rules.** This creates a second, unsynchronized rule path, which AGENTS.md prohibits.
- **Datalog/OWL reasoner.** Excess complexity for six rules.

## Consequences

- The "ontology vs procedural parity" comparison in MVP design §13 can be run per engine class.
- Explanations shown in the UI come from inventory descriptions plus findings, never from prompt text.

## Verification

- The inventory completeness check above.
- Engine `ERROR` (for example a malformed shape) blocks the write with a distinct diagnosis.
