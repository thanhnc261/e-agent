# Plan sections

In this order. A missing section is a plan defect.

1. **Header:** `# <Phase> Implementation Plan`, the agentic-workers note, **Goal** (one sentence), **Architecture** (two or three sentences), **Tech Stack**, **Spec** (the roadmap row, design sections and ADRs this plan argues from).
2. **Global Constraints:** project-wide rules copied with exact values: gate commands, branch, commit trailer, boundaries, "no behaviour change" where it applies.
3. **Review Focus:** the five input classes or failure modes the tests do not exercise, each pinned to the task that adds its test.
4. **Design refs:** the design sections implemented, by file and section number.
5. **ADRs:** the ADRs implemented or required, with status; a Proposed ADR blocks the merge until accepted.
6. **Toggles and fallback:** every runtime feature with its toggle name, the `off | shadow | on` behaviour and the fallback boundary.
7. **Gate:** the gate set per task (`quick`, `full`, `pg`, `e2e`) and the end-of-phase levels (full gate, Postgres run, `make e2e`, live check).
8. **Live check:** what the live check on `odoo19-learning` exercises at the end of the phase, and what it may not touch.
9. **Tasks:** `### Task N: <name>` with Files, Interfaces (consumes, produces), and checkbox steps: failing test, run to see it fail with the expected message, implement, run to see it pass, commit.
10. **Self-review:** spec coverage, placeholder scan, type consistency, Review Focus coverage.
