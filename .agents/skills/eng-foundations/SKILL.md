---
name: eng-foundations
description: Engineering standard for e-agent (ENG-* rules by ID). Read before any engineering task or review.
---

# Engineering foundations

This is the standard engineering work is built and reviewed against. It indexes the repository's binding rules by ID so that other skills, reviews and handoffs cite them instead of restating them.

## Authority

- `AGENTS.md`, `docs/roadmap.md` (Rules) and accepted ADRs are the source of every rule here. This skill names them by ID; it never weakens them. Where this file and a source disagree, the source wins and this file is fixed.
- Rules are cited by ID (`ENG-…`). Do not copy rule text into plans, reviews or handoffs.
- A rule change needs the owner. IDs stay stable: retire a rule, never renumber one.
- A Blocker finding rests on a rule whose enforcement is `gate`, `test`, `hook` or `permission`, or on an accepted ADR. A `review`-only rule justifies at most High.

## Reading order

1. [rules.md](references/rules.md): the rules, grouped by area, each with its source and how it is enforced.
2. [gotchas.md](references/gotchas.md): mistakes already made once, so they are not made twice.
3. The `AGENTS.md` section or roadmap rule a rule's `Source` names, when the wording matters.

## Rules for every use

- Evidence before claims: a gate result, a test name, a file and line, or a commit. "Should pass" is not evidence.
- Fixtures and live results are reported separately. A skipped check is named, never silent.
- Model output is a proposal; nothing a session writes grants approval or marks its own work verified.
- The same correction twice becomes a gotcha, a rule, a skill line or a hook, in the same change (ENG-WORK-3).
- Keep the main context small: read the rule you need, not the whole standard, and delegate large reads to a fresh context.

## Changing the standard

Add a rule only with a source in `AGENTS.md`, the roadmap or an accepted ADR. Keep each rule's four fields on one line each. Run `uv run python scripts/check_agent_skills.py`; it rejects unknown IDs, missing fields and unknown enforcement kinds. Durable changes need owner approval; record it in the handoff.
