# Study 05: identity refinement and truthful states

Date: 2026-10-11. Status: candidate mockup, not product implementation. Brief: `research/17-agentic-chat-v5-brief.md`. Standard: ag-ux-foundations at 5a2852b. Built with the `ag-ux-mockup` skill.

## What changed

v5 keeps study 04's conversation-first composition and design system. It changes three things.

**1. Identity.** The connected-node mark is rendered at the owner's pose: 15° clockwise, 35° backward tilt, subtle depth (`depth: 1`), no shadow, glossy surface. It goes through `logoGlyphFor(...)` in the v4 `design-system/brand.js`; the geometry is not forked.

**2. Colour.** The light-theme `color.brand` deepens from `#619581` (3.23:1 on canvas) to `#4f8a74` (3.79:1), staying in the Soft Lagoon hue.
- **Why:** the shadowless, shallow mark relies on its face colour alone.
- **Unchanged:** the dark and high-contrast brand roles, and all action accents.
- **Where:** the override lives in `v5.css`. The v4 token sources are untouched.

**3. Truthful states and safeguards.** These fix the highest-severity findings of `../agentic-chat-v4/GAP-AUDIT.md`:
- **F-1:** new states for sending (executing), committed but checking, and failed with nothing created.
- **F-2:** an AI disclosure with capabilities and limits at entry, an "AI agent" author label, and an AI-origin marker on drafted content.
- **F-3:** a Working state with recorded milestones (no percentage or ETA), a persistent status, and **Stop** available while working, sending and checking. Stopping in flight leads to "outcome unknown" with no resend.
- **F-4:** "What happens if you approve" shows the effect and reversibility on the document and in the confirmation. The acting identity and connection are uncollapsed, and the decision row is sticky.
- **F-6:** every prototype-only control moved into a dashed **Study controls** strip above the app. It stands in for server events and is not part of the product.
- **F-9:** in-page theme selection (System, Light, Dark, High contrast) that honours the OS preference, and `aria-current` with a 3:1 inset bar on the selected conversation.
- **F-15:** a Failed state with cause and next step.

## Open

From the repository root:

```sh
python3 -m http.server 4181 --bind 127.0.0.1 --directory research/mockups
```

- Conversation study: http://127.0.0.1:4181/agentic-chat-v5/
- Identity: http://127.0.0.1:4181/agentic-chat-v5/identity.html

## What to evaluate

1. **The new mark.** Open the identity page and compare v4 and v5 side by side. Check the mark at 24 and 32 px, and in the dark and high-contrast themes. Is the shadowless, shallow, glossy pose still clearly "connected nodes"? Is the deeper colour right?
2. **Entry.** Does the AI disclosure read as honest and useful, or as clutter, above the composer?
3. **Draft an order** shows Working. Try **Stop**, then **Study controls → Restart → Finish preparing**. Read "What happens if you approve" before approving.
4. **Approve.** You should see Sending, then (Study controls) Committed · checking, then Verified. Repeat with **Execution fails**, and with **Stop** while sending.

## State map

| Normative state | How to reach it | Notes |
|---|---|---|
| Ready | Open the study | Disclosure, capabilities and limits |
| Working | Start any example | Recorded milestones only. Stop available |
| Needs input | Prepare a handoff → Study controls → Finish preparing | Asks who should receive it in the conversation; Stop available. **Change audience** on the review creates a new revision (AG-CTRL-2) |
| Blocked by rules | Not reachable | Out of scope in the brief |
| Awaiting decision | Study controls → Finish preparing | Consequence block, identity and connection, sticky decision row |
| Decision invalidated | Study controls → A source changes | Names the changed source |
| Rejected | Reject | No action sent |
| Executing | Approve this action | "Sending approved action". Stop available |
| Verifying | Study controls → System confirms commit | "Committed · checking result" |
| Outcome uncertain | Stop while sending or checking, or Study controls → Connection lost | No resend; check result |
| Failed | Study controls → Execution fails | Cause and next step; nothing created |
| Cancelled or stopped | Stop while working | Nothing proposed or sent |
| Verified complete | Study controls → Read-back matches | Separate read-back evidence |

**Not redrawn in this slice:** the embedded or docked overlay composition. The identity page shows the 48 px launcher, the app tiles and the author mark at the v5 pose. The full docked specimen remains `../agentic-chat-v4/overlay.html`, which still shows v4's pose. It is the next slice's first item.

## Reused and changed

| Source | Used as | Changed here |
|---|---|---|
| `../agentic-chat-v4/styles.css` and `design-system/*` | Linked or imported | Nothing. v5 additions are in `v5.css` and `identity.css` |
| `../agentic-chat-v4/design-system/brand.js` | `logoGlyphFor(pose)` | Parameters only (`identity.js`) |
| `../agentic-chat-v4/chat-content.js` | Imported | Nothing |
| `../agentic-workspace-v3/fixtures.js` and `action-model.js` | Imported | Nothing |
| `../agentic-chat-v4/app.js` and `index.html` | Copied, then modified as v5 `app.js` and `index.html` | See "What changed" |

## Sample data

Every example, person, organization, access check and result is fictional and labelled as a sample in the interface. Nothing calls a model or a live system.
