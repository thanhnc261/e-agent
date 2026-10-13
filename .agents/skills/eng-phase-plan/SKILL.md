---
name: eng-phase-plan
description: Turn a roadmap phase into a detailed plan and feature list; stops for owner review.
---

# Engineering phase plan

A phase starts only after its plan exists, is linked from the roadmap and is reviewed (ENG-PLAN-1). This skill writes that plan and the feature list the harness materialises tasks from.

## Hard limits

- Read [eng-foundations](../eng-foundations/SKILL.md) first; cite rules by ID.
- The plan implements design sections and ADRs named in the roadmap row; a contract or boundary change needs an ADR first (ENG-PLAN-2).
- No implementation in the planning session. The plan is the deliverable; the owner reviews it before any `new-task`.
- Every runtime feature in the plan names its toggle and fallback (ENG-TOGGLE-1, ENG-TOGGLE-2).

## Workflow

1. **Read the sources.** The roadmap row for the phase and its dependencies; the design sections and ADRs the row cites; the previous phase's handoff in `docs/handoffs/`; `docs/plans/` for the sibling plans' form.
2. **Write the plan** at `docs/plans/<YYYY-MM-DD>-<phase-slug>.md` with the sections in [plan-sections.md](templates/plan-sections.md), in that order. Tasks are bite-sized, each with checkbox steps that name the failing test, the command and its expected output, and the commit.
3. **Write the feature list** at `harness/state/<phase>/features.json`: one entry per task, `id` `F-<phase>-<n>`, `category` the part it touches, `description` one sentence, `steps` the task's verification steps, `passes` false. Start from [features.json](templates/features.json), or build it entry by entry with `uv run e-agent-harness add-feature`. Validate it:

   `uv run e-agent-harness validate features harness/state/<phase>/features.json` must print ok.

4. **Link the plan** from the roadmap's phase table and run `uv run e-agent-harness validate-context` (the manifest's active plan and required sections are checked).
5. **Self-review** the plan against the spec: every requirement has a task, no placeholders, names consistent across tasks, a Review Focus line for each failure mode the tests do not cover.

## Before handing off

- [ ] Every mandatory section is present and non-empty.
- [ ] Every task has a test step, a command with expected output, and a commit step.
- [ ] The feature list validates and has one entry per task.
- [ ] The roadmap links the plan; `validate-context` prints ok.

## Stop gate

The owner reviews the plan and names it approved. A general instruction to continue is not approval. Record the approval in the plan's status line.
