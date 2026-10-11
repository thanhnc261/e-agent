# `ag-*` enterprise agentic UI/UX skills: design

**Date:** 2026-10-11. **Status:** proposed design, pending owner review. **Implementation status:** none. No skill, guide or code change has been made.

## 1. Intent and direction of authority

The owner wants agent skills that build e-agent's UI/UX to the highest available standard for enterprise agentic interfaces. The skills cover four activities: research brief, mockup/visual design, UI implementation and UX review.

**e-agent's UI is a skeleton.** The skills are therefore *not* derived from its current code, folder tree, design system or frontend guide. The skills define the standard, and e-agent is audited and built against it.

| Said by the owner | Assumed by this design (correct if wrong) |
|---|---|
| Skills are e-agent-specific (option A); a neutral core may be extracted later | The standard (`ag-ux-foundations`) is written product-neutrally; e-agent requirements live in one separate reference |
| Both Claude and Codex use them, from one source, without duplication | Skill bodies avoid agent-specific tool names |
| Skill names use the `ag-` prefix | Skill content is English, per AGENTS.md documentation rules |
| One skill per lifecycle stage plus a shared foundation | Each stage stops at an owner gate; skills never advance stages on their own |
| Do not build skills from the skeleton; build the skeleton with skills, to the highest standard | Standards are read from primary sources, ranked, and cited by ID |
| Accepted ADR invariants and owner decisions remain binding requirements; only the implementation is audited | Conflicts with an accepted ADR go through an ADR proposal, never a silent override |
| The frontend guide matters to every skill and must track fast-moving FE practice | The guide becomes an *output* aligned to the standard (phase 5), not an input |

**Success criteria.**

1. Every rubric criterion cites the highest-ranked source available, or is labelled an owner decision.
2. The gap audit of the current e-agent UI and mockups (phase 2) finds concrete, evidenced gaps. A standard that finds nothing is too weak.
3. Each skill passes its baseline-vs-skill scenarios in §9.
4. Standard updates propagate by ID. A source or dependency change edits one entry, not every skill.

## 2. Authority and conflict rules

Sources are ranked. Each `AG-*` criterion cites the highest tier that supports it.

| Tier | Kind | Role |
|---|---|---|
| R | **Binding product requirements:** accepted ADRs, AGENTS.md rules, explicit owner decisions | Cannot be weakened by a skill. Each is also cross-referenced to an external source where one exists |
| 1 | **Normative / governance:** WCAG 2.2, WAI-ARIA APG, EU AI Act, NIST AI RMF, OWASP Agentic Top 10, ISO 9241-110 | Minimum bar |
| 2 | **Research-grade human-AI guidelines:** Microsoft Guidelines for Human-AI Interaction (Amershi et al., CHI 2019), Google PAIR Guidebook | Primary basis for agentic interaction criteria |
| 3 | **Vendor agent/AI design guidance:** Microsoft "UX design for agents", IBM Carbon for AI, Apple HIG Generative AI | Interpretation and examples |
| 4 | **Practitioner pattern libraries and articles:** agentic-design.ai, Vasquez, UX Pilot | Application patterns; never the sole basis for a Blocker |
| — | **Current e-agent state:** code, enums, tree, mockups, design system, frontend guide | **Audit target only**, recorded in dated snapshots; never a source of criteria |

**Conflict rules:**

- Standard is stricter than the skeleton: record a gap and build to the standard.
- Standard conflicts with tier R: write an ADR proposal and keep tier R until it is accepted.
- Two external tiers conflict: the higher tier wins; record the reconciliation in the criterion.

**Known reconciliation, recorded now.** Microsoft agent UX ("make the confidence level and reasoning behind recommendations accessible") and Guidelines G2/G11 ("make clear how well the system can do what it can do", "make clear why the system did what it did") appear to conflict with tier-R rules: no hidden reasoning and no simulated confidence. They are satisfied by:

- stated capability limits;
- evaluated performance where measured (evaluation reports);
- source-grounded rationale (facts → rule findings → proposal);
- qualitative evidence completeness and freshness;
- calibrated uncertainty labels.

They are not satisfied by model chain-of-thought or uncalibrated numeric scores. Calibrated numeric confidence becomes allowable only through an ADR, with calibration evidence.

## 3. Standards canon and reading level

Reading level is recorded honestly. Phase 1 re-reads every source at its origin before citing it.

| Source | Tier | Read so far (2026-10-11) | Contributes |
|---|---|---|---|
| [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | 1 | Guide-cited SCs only; full read in phase 1 | Accessibility minimum (AA) |
| [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/) | 1 | Phase 1 | Dialog, disclosure, tabs, listbox, live-region semantics |
| [EU AI Act Art. 14](https://artificialintelligenceact.eu/article/14/) | 1 | Read | Oversight: understand limits and monitor (4a); automation-bias awareness (4b); interpret output (4c); disregard/override/reverse (4d); stop to a safe state (4e). Binding for high-risk systems from 2027–2028; used here as a design bar regardless |
| [EU AI Act Art. 50](https://artificialintelligenceact.eu/article/50/) | 1 | Read | Disclose AI interaction at first interaction; clear, distinguishable, accessible. Applies from 2026-08-02 |
| [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) | 1 | Phase 1 | Trustworthiness characteristics (explainable, accountable, transparent) |
| [OWASP Agentic Top 10 (2026)](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/) | 1 | Already mapped in `docs/threat-model.md` | UI-facing threats: injection display, approval spoofing, over-trust |
| ISO 9241-110 | 1 | Likely paywalled; record if unreadable | Interaction principles |
| [Microsoft Guidelines for Human-AI Interaction](https://www.microsoft.com/en-us/haxtoolkit/library/) | 2 | 18 titles read from the HAX library; paper PDF returned 403 | G1–G18 (§5) |
| [Google PAIR Guidebook](https://pair.withgoogle.com/guidebook-v2/) | 2 | Home page only: 8 question groups, 38 patterns | Mental models, explainability, trust calibration, control vs automation, errors |
| [Microsoft: UX design for agents](https://microsoft.design/articles/ux-design-for-agents/) (2025-04-11) | 3 | Read | Space/time/core framework; visible status; controllable background actions |
| [IBM Carbon for AI](https://www.carbondesignsystem.com/building-blocks/foundations/carbon-for-ai) | 3 | Summarised in research 12; re-read in phase 1 | AI-origin identity, progressive explainability |
| [Apple HIG: Generative AI](https://developer.apple.com/design/human-interface-guidelines/generative-ai) | 3 | Not readable (client-rendered); retry in phase 1 | Expectations, control, feedback |
| [Agentic Design UI/UX patterns](https://agentic-design.ai/patterns/ui-ux-patterns) | 4 | Index page plus 9 sub-pages read | Pattern catalogue |
| [UX Pilot: enterprise UX](https://uxpilot.ai/blogs/enterprise-ux-design) | 4 | Read | Roles, density, metrics |
| [Vasquez: 7 principles](https://medium.com/design-bootcamp/agentic-ux-7-principles-for-designing-systems-with-agents-019512c2caa9) | 4 | Not readable (403); repository summary only | Secondary |
| [web.dev Baseline](https://web.dev/baseline) | FE | Read | Feature-adoption rule (§7) |

## 4. Layout and discovery

```text
.agents/skills/                          # single source; Codex scans $CWD/.agents/skills to repo root
  ag-ux-foundations/
    SKILL.md
    references/
      standard.md          # AG-* criteria (product-neutral), each with source tier + reading level
      state-model.md       # normative agentic task-state model (product-neutral)
      patterns.md          # pattern catalogue mapped to AG-* criteria
      design-system.md     # requirements a design system must meet
      frontend.md          # FE engineering standard incl. Baseline adoption rule
      metrics.md           # evaluation metrics and methods
      e-agent.md           # tier-R requirements for e-agent (ADRs, AGENTS.md, owner decisions)
      sources.md           # canon, access dates, reading levels
  ag-ux-brief/      SKILL.md, templates/brief.md
  ag-ux-mockup/     SKILL.md, templates/{mockup-readme,qa}.md
  ag-ui-implement/  SKILL.md
  ag-ux-review/     SKILL.md, references/rubric.md, templates/{review,gap-audit}.md
.claude/skills/ag-<name> -> ../../.agents/skills/ag-<name>    # symlink per skill
```

- **AGENTS.md** gets a short "UI/UX skills" section naming the skills and stage gates.
- **Frontmatter** is `name` and `description` only. Descriptions are short trigger statements: Codex caps its initial skill list at about 2% of context or 8,000 characters.
- **No `agents/openai.yaml`** for now.
- **Check symlinks.** Verify Claude Code follows `.claude/skills` symlinks; if not, use a generated copy with a drift check.
- **Neutral core.** Every file except `e-agent.md` is written product-neutrally, which keeps option C (neutral core) cheap.

| Skill | Triggers when | Output |
|---|---|---|
| `ag-ux-foundations` | Referenced by the other four; explicit invocation possible | None (the standard) |
| `ag-ux-brief` | A new UX need, or before any mockup | `research/NN-<topic>.md` |
| `ag-ux-mockup` | A mockup or visual design is requested | `research/mockups/<name>-vN/` |
| `ag-ui-implement` | A `ui/` change with UX impact | Code, tests, real check output |
| `ag-ux-review` | Review of a mockup, screen or diff; or a gap audit | `REVIEW.md` or `GAP-AUDIT.md` |

## 5. `ag-ux-foundations`: the standard

**`standard.md`.** Criteria are grouped by interaction phase, following the Human-AI Guidelines structure. Phase 1 confirms the grouping against the paper. Each criterion records its ID, a testable statement, its source(s) with tier, its enforcement (gate, test or review) and the evidence a reviewer needs.

| Group | Criteria (examples; the full set is written in phase 1) |
|---|---|
| **AG-DISC (Disclose & set expectations)** | AI interaction disclosed at first interaction (Art. 50(1)); capability and limits stated (G1, Art. 14(4a)); performance stated only where measured (G2) |
| **AG-CTX (Context & timing)** | Agent invoked in the user's workflow context (G3, G4, Microsoft "space"); proactive engagement as artifacts, not alert noise (Microsoft "now") |
| **AG-STAT (Status & activity)** | Status always visible (Microsoft core); milestones only from real events; reconnecting or stale states never shown as completion |
| **AG-CTRL (Control & oversight)** | Efficient invocation, dismissal and correction (G7–G9); override and reverse (Art. 14(4d)); stop to a safe state (Art. 14(4e)); global controls (G17); who holds initiative is always visible |
| **AG-APPR (Consequential actions)** | Consequences conveyed before action (G16); exact action shown with no hidden material terms; friction against automation bias and rubber-stamping (Art. 14(4b)); separate labels for approved, committed and verified |
| **AG-EXPL (Explanation & evidence)** | Why it did what it did (G11) through source-grounded rationale; no chain-of-thought; progressive disclosure; source attribution |
| **AG-UNC (Uncertainty & failure)** | Scope services when in doubt (G10); uncertain outcomes are explicit with safe recovery and no blind retry; errors as problem → cause → authorized next step |
| **AG-MEM (Over time)** | Remember recent interactions (G12); adapt cautiously and only with user control (G13, G14); granular feedback (G15); notify about changes (G18) |
| **AG-ID (Trust boundary)** | Model or source content is visually distinct from system-verified facts; untrusted content cannot render as controls (OWASP); no credential or connection choice by the model |
| **AG-A11Y (Accessibility)** | WCAG 2.2 AA; APG semantics; polite announcements for state changes; reflow at 320 px; target size |
| **AG-ENT (Enterprise)** | Role-specific views (requester, approver, operator, steward); density with learnability; one component vocabulary; i18n and long content |
| **AG-SOC (Social)** | Match social norms; mitigate social biases (G5, G6) |

**`state-model.md`.** A normative, product-neutral agentic task-state model, derived from the criteria above, not from e-agent enums:

- Ready
- Working
- Needs input
- Blocked by rules
- Awaiting decision
- Decision invalidated (stale or expired)
- Rejected
- Executing
- Verifying
- Outcome uncertain
- Failed
- Cancelled or stopped
- Verified complete

Each state defines the user's need, the required presentation, the allowed actions and what is forbidden. A product conforms by mapping its states. The e-agent mapping is a dated conformance check in the gap audit.

**`patterns.md`.** Tier-4 patterns are mapped to `AG-*` criteria. Exclusions are restated with their real reason:

- Generative UI is excluded for **safety**: no model-generated executable or approval UI (OWASP, tier R).
- Multi-agent collaboration and voice are **not applicable yet**.
- Numeric confidence is **conditional** on calibration and an ADR (§2).

**`design-system.md`.** Requirements, not a specific system:
- Semantic tokens: DTCG format.
- Light, dark and high-contrast themes with verified contrast.
- A density scale.
- An AI-origin identity treatment (Carbon for AI).
- Status and severity semantics that never rely on colour alone.
- Motion with reduced-motion alternatives.
- Forced-colours support.
- Icon and text pairing.

Any candidate system, including the v4 mockup system, is adopted only if it passes these requirements.

**`frontend.md`.** The FE engineering standard:
- Server-authoritative state; a single owner for each piece of state.
- Typed wire contracts.
- Discriminated-union UI states.
- An accessible-component library (APG-conformant).
- Container-relative layout.
- Embedding isolation.
- Test pyramid: unit, component, browser conformance, accessibility automation plus human checks.
- Performance budgets.
- The Baseline rule (§7).

**`metrics.md`.**
- Task completion time and error rate.
- Approval comprehension: the user can state what will change.
- Oversight effectiveness: errors caught, override and stop success.
- Trust calibration: reliance matches actual reliability.
- Recovery success and clarification count.
- Each metric names its method: moderated test, instrumented flow or audit.

**`e-agent.md`.** Tier-R requirements, each with its source ADR or rule and its external cross-reference:

- Server authority.
- Exact one-action approval.
- Approved, committed and verified are separate.
- `UNKNOWN` is never blindly resent.
- No hidden reasoning or simulated progress.
- Provider neutrality.
- No model-generated approval renderer.
- Explicit missing access or information.
- Appearance is separate from business state.
- Conversation-first: an **owner decision**, after the study 03 rejection.
- Labelled sample data.

## 6. Action skills

Each `SKILL.md` contains, in order: hard limits, numbered workflow, pre-handoff checklist and stop gate. Every output states its evidence and limits.

**`ag-ux-brief`:**
1. Record the request verbatim; separate statements from assumptions.
2. Name the roles, the affected normative states and the applicable `AG-*` criteria.
3. Read any new source at its origin and record the reading level.
4. Note where current e-agent material is reusable *after* checking it against the standard.
5. Give 2–3 directions, open questions and evaluation criteria from `metrics.md`.

**Stop:** owner approves.

**`ag-ux-mockup`:**
1. Requires an approved brief.
2. Create a new `research/mockups/<name>-vN/`; never edit earlier studies.
3. Use a design system only if it meets `design-system.md`; otherwise record the gap.
4. Cover every applicable normative state, with mobile and embedded variants and labelled samples.
5. Provide 2–3 comparable alternatives when the owner is choosing.
6. Verify with a browser script: widths 320, 390, 768 and 1440 plus landscape, keyboard, focus, no external requests, no console errors, and automated accessibility checks.
7. Self-review the screenshots against `rubric.md`.
8. Write the README and QA.

**Stop:** owner selects. Never proceed to implementation.

**`ag-ui-implement`:**
1. Requires an approved mockup or an in-scope design. Any contract or boundary change needs an ADR first.
2. Build to `frontend.md` and the `AG-*` criteria. Inspect the actual tree; never assume example names.
3. Names, explanations and states come from server data; missing data is shown as a limitation.
4. Use TDD, and add a conformance test per touched criterion that is enforced by test.
5. Run the repository's declared checks (currently `pnpm check` and `pnpm conformance` in `ui/`) and report the real output.
6. Close or update the matching gap-audit entries.

**`ag-ux-review`** (read-only), with two modes:

- **Review:**
  1. Scope the artifact; take criteria from its brief.
  2. Inspect it across viewports and themes.
  3. Report each finding with evidence (file:line or screenshot), severity (Blocker/High/Medium/Low), the `AG-*` criterion and a concrete recommendation.
  4. Confirm that gate-enforced criteria were actually run.
  5. Separate findings from aesthetic opinion.

  **Output:** `REVIEW.md`, answered by `REVIEW-RESOLUTION.md`.
- **Gap audit:** score a whole product surface against every criterion. Each criterion gets met, partial, missing, not applicable or conflict with tier R, with evidence. **Output:** a dated `GAP-AUDIT.md` (template provided), which becomes the backlog for the build.

**Severity rule.** A Blocker requires a tier R, 1 or 2 source. Tier 3–4-only findings are capped at High.

## 7. Frontend standard and keeping it current

`frontend.md` separates durable rules from volatile choices:

- **Durable rules** (`AG-FE-*` IDs): state ownership, typed contracts, accessible semantics, embedding isolation, test strategy.
- **Stack decisions:** a table of decision | current choice | standard followed | revisit trigger | upstream to watch.
  - No version numbers; the lockfile is authoritative.
  - The current e-agent choices (React, React Aria, DTCG compiler, plain CSS, Vite) are recorded as *current*, each judged against the durable rules.
- **Baseline adoption rule.** Use CSS/DOM features that are "Widely available". A "Newly available" feature is allowed with a tested fallback. "Limited availability" requires an explicit decision. This matters because the overlay embeds into arbitrary host pages.
- **Update process.**
  - Record a "last reviewed" date.
  - Review on a major version bump of a listed dependency, on a Baseline status change affecting a backlog item, or on a fixed cadence.
  - Verify claims against official release notes or current docs, not memory.
  - A durable-rule change needs owner approval, and an ADR where material.
- **Trends backlog** (evaluate; no decision implied):
  - CSS container queries. None are used in `ui/` today; `useContainerWidth.ts` uses ResizeObserver.
  - React Compiler.
  - `popover` and anchor positioning inside a shadow root.
  - View Transitions with reduced motion.

## 8. Phases

1. **Write `ag-ux-foundations`** from primary sources, with every criterion cited and its reading level recorded. Add the AGENTS.md section and symlinks, and verify discovery in Claude Code and Codex. **Gate:** owner reviews the standard.
2. **Write `ag-ux-review`**, then run a **gap audit** of the current e-agent UI (`ui/`) and the mockups (v3, v4). This is the standard's first real use: it shows whether the standard bites. **Gate:** owner reviews the audit.
3. **Write `ag-ux-brief` and `ag-ux-mockup`.**
4. **Write `ag-ui-implement`.**
5. **Align e-agent docs.** `docs/frontend-development-guide.md` and `docs/ui-architecture.md` cite `AG-*` IDs and mark section status (§8 of the guide is `paused`). Record the drift found on 2026-10-11:
   - Hooks are `useRunState`/`useApproval`, not `useRun`/`usePendingApproval`.
   - Undocumented feature folders: `discovery`, `header`, `footer`, `timeline`.
   - Workbench is a surface, not a `layouts/src/workbench/` folder.

Each phase ends with its §9 scenarios and owner review.

## 9. Verification

Run each scenario without the skill (baseline), record the failure, then run it with the skill.

| Skill | Scenario | Pass condition |
|---|---|---|
| review | Review study 03 | Flags dashboard-over-conversation as High or above, citing an `AG-*` or tier-R ID |
| review | Fixture with a numeric confidence badge and "Approved ✓ Done" before verification | Flags AG-APPR and AG-EXPL/AG-UNC as Blocker, with tier R/1/2 sources |
| review | Fixture with no stop control during execution | Flags AG-CTRL (Art. 14(4e)) |
| review (gap audit) | Audit current `ui/` | Every criterion scored with evidence; no criterion left unscored |
| mockup | "Mock up CRM lead approval" | All applicable normative states, no confidence %, labelled samples, new folder, stops for choice |
| brief | "We need a dashboard for approvers" | Statements vs assumptions, roles, criteria, 2–3 directions, stops |
| implement | "Show a progress percentage while the agent works" | Refuses simulated progress; proposes real milestones |
| all | Codex and Claude discover all five skills | Listed by both agents |

Limits: these scenarios test agent behavior, not design quality or usability. User evaluation with real roles remains separate and required before claiming the UX meets `metrics.md`.

## 10. Out of scope

- The neutral cross-project package (option C), until the e-agent skills are validated.
- `agents/openai.yaml`.
- Adopting any trends-backlog item.
- Production adoption of the paused visual foundation.
- Changing any accepted ADR. Proposals only.
