# Scoring rubric

This rubric is a procedure. It applies the standard; it never adds criteria. Criterion content lives only in [standard.md](../../ag-ux-foundations/references/standard.md), [design-system.md](../../ag-ux-foundations/references/design-system.md), [frontend.md](../../ag-ux-foundations/references/frontend.md) and [e-agent.md](../../ag-ux-foundations/references/e-agent.md).

## 1. Scores

Give each criterion or requirement in scope exactly one score.

| Score | Meaning | Evidence required |
|---|---|---|
| met | The artifact satisfies the statement in every mapped state | Where it was observed (file:line, screenshot, test name) |
| partial | Satisfied in some states, viewports or themes, but not all | Where it holds and where it fails |
| missing | Not satisfied, or the required state or element is absent | What was looked for and where |
| not applicable | The criterion's subject does not exist in this artifact (for example, no consequential action) | One sentence on why |
| conflict | Satisfying the criterion would violate a binding requirement | The criterion, the `EA-…` ID and a proposed decision change |

A `partial` or `missing` score produces a finding. A `conflict` produces a decision proposal, not a defect. The binding requirement stays in force until a decision changes it.

## 2. Order of checking

1. **Binding requirements first.** Score `EA-1` to `EA-16`. A violation may be rated Blocker, regardless of any AG cap.
2. **Criteria by Enforcement field:**
   - `gate` or `test`: confirm the check exists and was run on this revision. Record the command and its result. If no check exists, score from inspection and add a finding that the automated check is missing.
   - `review`: inspect in depth across viewports, themes and keyboard use. These criteria are where reviewers add the most value.
3. **State coverage.** Every normative state relevant to the artifact must be reachable. Check the Forbidden items for each state. Items tagged "(model rule)" are capped at Medium unless a listed criterion covers them.

## 3. Severity

- Start from the Max severity of every criterion the finding violates. Use the multiple-criteria rule in the standard's header: cite all violated IDs, and the finding may go up to the highest cap among them.
- Rate the actual effect at or below that cap:
  - **Blocker:** a person can be misled about what will happen or has happened, can lose work or authority, or cannot complete the task with assistive technology.
  - **High:** a significant risk of a wrong decision or a failed task, with a workaround.
  - **Medium:** friction or inconsistency without a wrong outcome.
  - **Low:** polish.
- A finding resting only on tier-3/4 sources is at most High.
- Write exactly one severity per finding. Never a conditional such as "High (Blocker under EA-5)". If a binding requirement is violated and the effect warrants it, the severity is Blocker. Cite the `EA-…` ID in **Violates**.

## 4. Finding format

```markdown
### F-<n> — <short title>

- **Severity:** Blocker | High | Medium | Low
- **Violates:** EA-…, AG-… (all that apply)
- **Where:** <file:line | screenshot path | state at viewport/theme>
- **Observed:** <what happens, factually>
- **Expected:** <what the cited criteria require; reference, do not restate>
- **Recommendation:** <a concrete change; name the owner layer if known>
```

## 5. Review-only checks that are easy to miss

These apply criteria without adding new ones. Each line names the criterion it applies.

- **Hierarchy.** Is the conversation the primary surface, with the artifact in a closable workspace and no dashboard competing with it (EA-10)?
- **Disclosure.** At first interaction, is the AI disclosed, and are its capabilities and limits stated in context (AG-DISC-1, AG-DISC-2)?
- **Stop.** Is a stop control reachable in every working and executing state, and does stopping report the status of any in-flight action (AG-CTRL-1)?
- **Decision surface.**
  - Is the exact action shown? (AG-APPR-1)
  - Are material terms visible without expansion? (AG-APPR-3)
  - Is confirmation proportional to risk, with approve not focused by default? (AG-APPR-4, AG-APPR-8)
  - Are stale or expired decisions blocked? (AG-APPR-5, AG-APPR-9)
- **Truthful outcome.**
  - Are decided, executed and verified separate? (AG-APPR-6, EA-3)
  - Does an unknown outcome offer a check, never a resend? (AG-UNC-2, EA-4)
- **No simulation.** Is there no invented progress, ETA, reasoning or numeric confidence (AG-STAT-2, AG-EXPL-4, EA-5)?
- **Origin and trust.** Are AI content, verified facts and user content distinguishable, and does untrusted text stay inert (AG-ID-1, AG-ID-2, AG-ID-6)?
- **Identity.** Are the acting identity and connection shown (AG-ID-5)?
- **Design system.** Does it ship three verified themes, a density scale, forced-colours support, icon-and-text status and polite announcements (EA-12 to EA-16, AG-DS-1 to AG-DS-7)?
- **Samples.** Is sample or fixture data labelled (EA-11)?

## 6. Limits statement (always include)

State which of these were not done:
- real assistive-technology testing;
- real-device testing;
- moderated user evaluation against [metrics.md](../../ag-ux-foundations/references/metrics.md);
- live integration.

Script and browser checks verify mechanics only.
