# Agentic chat v5: identity refinement and truthful-state design brief

Date: 2026-10-11. Status: approved by the owner for mockup, as recorded below. Standard: ag-ux-foundations at 5a2852b. Written with the `ag-ux-brief` skill.

## Request

> hoàn thành skill và start một design dựa vào các design của code
> http://127.0.0.1:4181/agentic-chat-v4/identity.html
> logo: 15° clockwise · 35° backward tilt · subtle depth · none shadow · glossy surface
> http://127.0.0.1:4181/agentic-chat-v4/components.html#identity
> có thể điều chỉnh màu chủ đạo nếu cần thiết

(Owner, 2026-10-11. Translation: "finish the skills and start a design based on the existing designs in the code [the v4 identity and component pages]; logo: 15° clockwise, 35° backward tilt, subtle depth, no shadow, glossy surface; the primary colour may be adjusted if necessary.")

| Said by the owner | Assumed (correct if wrong) |
|---|---|
| Start a design based on the v4 identity and component system | v5 keeps v4's conversation-first composition and design system, and evolves them rather than replacing them |
| Logo pose: 15° clockwise, 35° tilt, subtle depth, no shadow, glossy | "Subtle depth" is v4's existing `depth: 1` option. The pose becomes the v5 default everywhere the mark appears |
| The primary colour may be adjusted if necessary | Adjust only where a measured need exists. Keep the Soft Lagoon hue family the owner chose |
| — | The first v5 slice also fixes the highest-severity v4 gap-audit findings, so the new identity is not presented on a surface that fails the standard |

## Context

- **Extends:** study 04 (`research/16-conversation-workspace-revision.md`) and its v4 design system (`research/mockups/agentic-chat-v4/`), as plain paths (uncommitted on main).
- **Current-state evidence:** `research/mockups/agentic-chat-v4/GAP-AUDIT.md` (2026-10-11): 35 met, 39 partial, 8 missing, 21 findings.

## Roles and states

| Role | Need |
|---|---|
| Requester | Delegate work in conversation, see what the agent is doing, stop it, understand the outcome |
| Approver (same person in this study) | Decide on one exact action with its consequences visible, and not be rushed |

| Normative state | In scope | User need | Current gap |
|---|---|---|---|
| Ready | yes | Know it is an AI agent and what it can and cannot do | F-2 |
| Working | yes | See real activity; be able to stop | F-3 |
| Needs input | yes | Answer a focused question | F-14 |
| Awaiting decision | yes | See the exact action, its consequences and reversibility | F-4 |
| Decision invalidated | yes | Know what changed | F-7 (partial) |
| Rejected | yes | Know nothing was sent | met |
| Executing | yes | Know the approved action is being carried out | F-1 |
| Verifying | yes | Know the result is being checked independently | met |
| Outcome uncertain | yes | Know what is safe to do | met |
| Failed | yes | Know what failed and the next step | F-15 |
| Cancelled or stopped | yes | Know the safe state reached | F-3 |
| Verified complete | yes | See the verified result | met |
| Blocked by rules | deferred | — | Not in the v4 scenarios. Planned for a later slice |

**Placements:** the study covers desktop, tablet and mobile. The identity page covers the launcher, app tiles and author mark. The embedded or docked overlay composition is **excluded from this slice**. Its v4 specimen stays the reference until the next slice redraws it with the v5 mark.

## Criteria the design must satisfy

| Area | Binding (EA) | Criteria (AG) | Failing in v4 |
|---|---|---|---|
| Identity and colour | EA-12, EA-15 | AG-DS-1, AG-DS-2, AG-DS-4, AG-ID-1 | F-17 (logo outside the token contract) |
| Entry | EA-10 | AG-DISC-1, AG-DISC-2, AG-CTX-1 | F-2 |
| Working and stop | EA-5 | AG-STAT-1, AG-STAT-2, AG-CTRL-1, AG-CTRL-3 | F-3 |
| Decision | EA-2 | AG-APPR-1, AG-APPR-3, AG-APPR-4, AG-APPR-8 | F-4 |
| Outcome | EA-3, EA-4 | AG-APPR-6, AG-UNC-2, AG-UNC-3 | F-1, F-15 |
| Prototype honesty | EA-11 | AG-ID-1 | F-6, F-11 |
| Themes | EA-12, EA-16 | AG-DS-2, AG-A11Y-4, AG-STAT-4 | F-9 |

**Patterns:**
- Apply: Agent Status & Activity (without ETA), Mixed-Initiative, Human-in-the-Loop, Error Handling and Recovery, Onboarding and Education, Trust and Transparency.
- Limit: Confidence Visualization (none shown).
- Exclude: Generative UI.

## Directions

### A. Evolve v4 with the new identity and truthful states (recommended)

- **Description:** Copy v4's chat composition into a new v5 folder, importing the v4 design system unchanged. Render the mark through `logoGlyphFor({rotation: 15, tilt: 35, depth: 1, shadow: "none", finish: "glossy"})`. Deepen the light-theme brand colour one step. Fix gap-audit findings F-1, F-2, F-3, F-4, F-6, F-9 (theme selection and the selected-item state) and F-15.
- **Trade-offs:** The largest change set. It keeps everything the owner accepted in v4.
- **Makes easier:** AG-DISC, AG-CTRL-1, AG-APPR-6, EA-3, AG-DS-2.

### B. Identity-only refresh

- **Description:** Apply the new pose and colour to v4's pages only.
- **Trade-offs:** Fast, but it presents the new identity on a surface with a known Blocker (F-1).

### C. New composition

- **Description:** Redesign the layout from scratch.
- **Trade-offs:** It discards the conversation-first structure the owner already accepted (EA-10).

**Recommendation:** A.

## Colour decision

| Theme | `color.brand` (v4) | Contrast on canvas | v5 | Contrast |
|---|---|---|---|---|
| Light | `#619581` | 3.23:1 | `#4f8a74` | 3.79:1 |
| Dark | `#bedcca` | 10.62:1 | unchanged | — |
| High contrast | `#174d3e` | 9.69:1 | unchanged | — |

**Reason:** v4 relied on the cast shadow and the deeper sidewalls to separate the mark from the ivory canvas. The new pose removes the shadow and reduces depth, so the face colour alone must carry the 3:1 non-text contrast (S-01, SC 1.4.11; AG-DS-2). The hue stays in Soft Lagoon.

**Scope:** the change is an override of the semantic role inside v5. The v4 token sources are unchanged. Primary-action accents are not changed; they already meet their own contrast.

## Evaluation

| Metric | Method | Question |
|---|---|---|
| M-3 Approval comprehension | Moderated, role-matched | Can the user state what will change, where, and whether it can be reversed? |
| M-4 Oversight effectiveness | Moderated, with seeded errors | Do users find Stop and use it correctly? |
| M-6 Recovery success | Moderated | Can users act safely after a failed or uncertain outcome? |

Browser checks will verify: viewports, themes, keyboard path and focus return, no console errors, no external requests, and that every listed state is reachable. They will not establish design quality or usability.

## Open questions for the owner

1. Should the deeper light-theme brand colour also become the identity-page default, or stay limited to the v5 chat?
2. Is the "Blocked by rules" state worth a sample scenario in the next slice?
3. Should the density scale (F-5, EA-13) be the next slice's priority?

## Approval

The owner's /goal of 2026-10-11 names this design ("start a design based on the code's designs", meaning the v4 identity and components) and its direction (the v4 basis, the stated logo pose, and colour adjustment if needed). It is recorded verbatim above. Direction A is the only direction consistent with all three statements, so it is treated as the chosen direction. Mockup proceeds; production implementation stays blocked until the owner selects the mockup.
