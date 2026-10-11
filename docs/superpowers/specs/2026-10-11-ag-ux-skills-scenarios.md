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

**Discovery**, checked 2026-10-11:
- `codex debug prompt-input` lists all five skills.
- A headless `claude -p` session in the worktree lists all five through the `.claude/skills` symlinks.

**Limits:** these scenarios measure agent behaviour on one run each. They do not measure design quality or usability.
