# ag-* skills: baseline-versus-skill scenarios (spec §9)

Date: 2026-10-11. This is the evidence for spec §9 that the stage skills change agent behaviour. Each scenario ran as a pair of fresh Claude Sonnet subagents with identical task text:
- the baseline was told not to read `.agents/skills` or `.claude/skills`;
- the skill run was told to read and follow the named skill.

Both produced text only, and no files were written. One run per arm, so this is indicative, not statistical.

| # | Skill | Scenario | Baseline | With skill | Pass condition met? |
|---|---|---|---|---|---|
| S1 | ag-ux-review | Review study 03 (`research/mockups/agentic-workspace-v3`, the study the owner rejected for dashboard-over-conversation) | Top finding was untested accessibility (High). It did **not** flag the dashboard/catalog hierarchy. It found no Blocker. | F-1 **Blocker**: "Homepage catalog; the conversation is not the primary surface", citing EA-10 and AG-CTX-1, with line evidence. It also flagged missing high-contrast, density and forced colours (EA-12 to EA-14), and missing stop and failed states (AG-CTRL-1). | Yes |
| S2 | ag-ux-review | Fixture with 64% / ETA progress, "Confidence 92%", autofocused Approve, collapsed terms, "Approved ✓ Done" before verification, no stop | Two Blockers (premature success, no stop). Fake progress rated Medium. Numeric confidence called "unexplained" only. No IDs. | Blockers for premature success (EA-3, AG-APPR-6) and no stop (AG-CTRL-1). It flagged simulated progress and uncalibrated confidence under EA-5, hidden terms (AG-APPR-3), default focus (AG-APPR-8), identity (AG-ID-5) and sample labels (EA-11). | Yes, with one defect: it wrote conditional severities ("High (Blocker under EA-5)"). Fixed: the rubric now requires one severity per finding. |
| S3 | ag-ux-mockup | "Mock up CRM lead approval" (plan only) | It proposed showing a **confidence level** and a "low-confidence" state, with no stop control, no executing, verifying or uncertain states, and a lead queue as the first screen. | It requires an approved brief first, then uses a new versioned folder. It covers all 13 normative states, with conversation first (EA-10) and labelled samples (EA-11). It has no simulated progress or numeric confidence (EA-5) and a reachable stop (AG-CTRL-1). It self-reviews with the rubric and stops for owner selection. | Yes |
| S4 | ag-ux-brief | "We need a dashboard for approvers" | Reasonable discovery questions and a screen-led outline. No criteria and no alternative directions. | Separates said from assumed. Names roles and states, with AG-APPR criteria per state. Gives three directions with a recommendation (a decision queue over a metrics dashboard), plus metrics and open questions. Stops for approval. | Yes, with one defect: it chose research number 11, which is taken by uncommitted studies in the owner's checkout. Fixed: the skill now says to check uncommitted research files. |
| S5 | ag-ui-implement | "Show a progress percentage while the agent works" | It would add a backend progress field and a ProgressBar. It mentioned a possible standard conflict but did not stop and did not mention an ADR. | It refuses as worded, citing EA-5 (ADR 0015, ui-architecture §10), and confirms that no progress field exists in the client schema. It offers real recorded activity instead. It requires an ADR before any contract change, then tests first, `pnpm check` and `pnpm conformance`. | Yes |

## Re-runs after the review fix wave (commit 60e1851)

- **S2 (ag-ux-review),** using the committed fixture `2026-10-11-ag-ux-scenario-fixture.html`:
  - Every finding now has exactly one severity.
  - Premature success (EA-3, AG-APPR-6) and the missing stop control (AG-CTRL-1) are Blocker.
  - Simulated progress and numeric confidence are flagged under EA-5, but rated **High** by effect, not Blocker.
  - **Partial pass:** the §9 row expected a Blocker for the confidence badge. The rubric allows a Blocker for an EA violation but does not force one.
- **S4 (ag-ux-brief):**
  - It used `git worktree list` to find the owner's checkout and chose `research/17-…`. This is correct, because 11–16 are uncommitted there.
  - **Minor deviation:** it said it "would not pick a direction", although the skill requires one recommendation. Its outline still lists the directions.

## Not yet exercised

- **S3 (ag-ux-mockup)** was a plan only. The skill's first real execution is the v5 identity study.
- **Codex behaviour** was not tested; only Codex discovery was.
- **S1 is partly circular.** EA-10 was derived from the owner's rejection of study 03, so the skill was graded on the case it was built from.
- **Not reproducible:** one Sonnet run per arm, and no transcripts were kept.

## Phase 2 gap audit

`ag-ux-review` in gap-audit mode scored the v4 study (`research/mockups/agentic-chat-v4`, uncommitted on main), on Opus, against the standard at 60e1851.
- **Scores:** all 88 rows scored (16 EA, 72 AG): 35 met, 39 partial, 8 missing, 6 not applicable, 0 conflict. There are 21 findings.
- **Top findings:**
  - F-1 Blocker: no executing, committed or failed state after approval (EA-3, AG-APPR-6).
  - F-2 High: no AI disclosure, capabilities or AI-origin mark (AG-DISC-1, AG-DISC-2, AG-ID-1).
  - F-3 High: no working state or stop control (AG-CTRL-1).
  - F-4 High: consequences and reversibility missing; material details collapsed (EA-2, AG-APPR-1, AG-APPR-3).
  - F-9 High: low-contrast composer boundary and selected-state indicator, and no theme selector in the chat (EA-12, AG-DS-2, AG-A11Y-4).
- The standard found concrete, evidenced gaps (spec §1, success criterion 2).
- The audit was written as `GAP-AUDIT.md` inside the study folder.
- The product `ui/` gap audit was not run in this pass.

**Discovery**, checked 2026-10-11:
- `codex debug prompt-input` lists all five skills.
- A headless `claude -p` session in the worktree lists all five through the `.claude/skills` symlinks.

**Limits:** these scenarios measure agent behaviour on one run each. They do not measure design quality or usability.
