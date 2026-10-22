# Conversation thread mockup (v1)

Date: 2026-10-22. Status: candidate mockup, not product implementation; awaiting the owner's selection at gate G-C. Brief: [research 20](../../20-conversation-thread-brief.md), approved at G-B on 2026-10-21 (owner-delegated; the eight decisions are recorded in [the Phase 4 plan](../../../docs/plans/2026-10-20-phase4-conversation-chat.md), Task 4e.1, because research files are create-only). Standard: ag-ux-foundations at `3ab6d7c2`. Phase 4, Task 4e.2.

G-B chose direction A: run cards in the conversation and a closable side workspace. This study renders three variants **within A** on one shared procurement scenario, so the owner can choose the details: how dense the run cards are, how wide the workspace is and how it behaves when closed, and where the refusal hint sits. It extends study 04 (`../agentic-chat-v4/`, research 16) and keeps the v5 identity (research 17); neither is changed. It answers gap-audit findings F-1 (disclosure in the empty thread), F-2 (thread of runs), F-3 (closable workspace), F-4 (agent's words labelled), F-6 (citations and explanation), F-7 (grounded tone), F-8 (the server's refusal hint), F-9 and F-10 (server-sourced sidebar, legacy runs marked "last seen") and F-17 (container queries) in [the 2026-10-21 gap audit](../../../docs/reviews/2026-10-21-chat-surface-gap-audit.md).

## Open

From the repository root:

```sh
node research/mockups/conversation-thread-v1/verify.mjs --serve
```

Open http://127.0.0.1:4183/research/mockups/conversation-thread-v1/ . The script serves only this folder, the production token CSS (`ui/packages/tokens/src/generated/tokens.css`) and the owner logo (`ui/packages/components/src/primitives/brand/e-agent-mark.svg`); both are linked, not copied. The page needs to be served from the repository root for those two links.

The comparison page is `compare.html`; its screenshot is `screenshots/00-overview.png`.

## The three variants (all direction A)

| | A1 · Run cards | A2 · Folded runs | A3 · Wide workspace |
|---|---|---|---|
| Run cards | Every message stays in the thread; a medium run card ends each run (status, one result line, Open, Stop on the active run) | Ended runs fold to a one-line row with "Show messages (n)"; only the latest run shows its messages | Rich card: status, result line, the earlier runs used as hints, and the grounded or verified note |
| Workspace | About 40 % of the width (22–34 rem), beside the thread | Narrow and fixed (24 rem); the approval table stacks into rows | About 52 % (28–48 rem); when closed on desktop, a reopen bar keeps the latest run's status in view |
| Refusal hint | Inside the composer, above the text | One line under the composer, beside Send | A callout above the composer with "Go to the decision" or "Read the run again" |

Fixed in every variant (brief, "Fixed for every direction", and G-B):

- The workspace opens by itself on desktop for a decision or a result, never for a reply, and can be closed; Escape and the close control return focus to the run card's Open (G-B 6, EA-10, AG-A11Y-2). Below 60 rem of app width it is a full view that switches with the conversation, with "Back to conversation".
- One composer. A message sent while a run works or waits for a decision is refused with the server's fixed hint; the composer stays open, the draft is kept and the approval card does not change (G-B 4).
- An answer to a run that has ended is refused with "the question changed; read it again" and the draft is kept (G-B 3, ADR 0023 §4 as amended in 4d.6).
- The agent's words are labelled on the message and on the result (G-B 5).
- The approval card is today's card: same fields, gates and confirm step (ADR 0034 §5 deferred at G-A). It moves into the workspace; its content does not change.
- Legacy runs sit in their own sidebar group "Earlier tasks · this session · last seen" (G-B 2).
- VI copy is the brief's accepted drafts where the brief gives them (G-B 7); every other new VI string here is a mockup draft. `strings.js` names the strings taken from the brief and from `i18n.ts`; everything else in it is new and needs confirmation at G-D.

## What to evaluate

1. Open `compare.html` (or `screenshots/00-overview.png`) and compare the three variants at the same moment: run 2 waits for approval and a typed message was refused.
2. Walk the scenario by keyboard in one variant: in "Thread empty" type `hi` and press Enter, then any text at each step (the sample continues with its recorded messages: "which products are short?", "draft a PO for it", "40"). At "Running" use **Show the next recorded event (sample)**. At the decision, type a message (it is refused), then Review and approve → Confirm. Then **Show the verified sample**.
3. Close and reopen the workspace on desktop; narrow the window below about 960 px to see the view switch.
4. Look at the grounded result (citations, "Value not recorded", the unmatched source, the explanation) next to the verified one, and decide whether the difference is clear (brief metric M-5).
5. Switch the prototype controls to Tiếng Việt, Dark, High contrast and Docked.

## State map

Every state is reachable from the **Sample state** control and by URL, for example `index.html?variant=a1&state=refused&lang=en&theme=light&surface=page`.

| Brief state | Normative state | `state=` | Notes |
|---|---|---|---|
| Thread empty | Ready | `empty` | AI disclosure and "What it can and cannot do" in the thread itself (F-1); examples only fill the box |
| Reply pending ("Your turn") | Needs input | `reply` | "Reply · not a verified result" once per thread; the composer says "Answering run 1" |
| Clarification ("Your answer is needed") | Needs input | `clarification` | Answer bound to run 2's question (`reply_to`) |
| Running | Working | `running` | The last recorded event only; no progress estimate; Stop on the run card and under the composer |
| Waiting approval | Awaiting decision | `approval` | Workspace opens by itself on desktop with the unchanged card |
| Waiting approval, with a refused message | Awaiting decision | `refused` | Server hint, draft kept, card unchanged; the message is not added to the thread |
| Verified | Verified complete | `verified` | Verified record, values and independent check; the agent's words labelled apart from them |
| Grounded | none: product state (grounded answer) | `grounded` | Neutral tone, grounded explanation line, citations with "Value not recorded" and "A source that could not be matched" |
| Failed | Failed | `failed` | Problem, cause, next step, "Nothing was written"; the thread continues |
| Answer to a run that ended | Failed (the message); its run is Cancelled or stopped | `ended-answer` | "The question changed. Read it again before answering." with the draft "40" kept |
| Per-run fallback | not a task state: a mode | `fallback` + `mode=off\|shadow\|features\|route-error` | Today's per-run view: card inline, inspector beside it, locked composer while a decision waits; a features-read failure is stated; a shadow route error keeps the draft and does not re-post |
| Legacy runs | not a task state: a sidebar placement | `legacy` | Separate group marked "last seen"; opening one shows the status read now ("Task cancelled") beside the one last seen ("Needs review") |
| Other normative states inside a run | Blocked by rules, Decision invalidated, Rejected, Executing, Verifying, Outcome uncertain, Cancelled or stopped | `gallery` | Reference sample: each as its run card shows it, with its stop control; Outcome uncertain offers "Check operation status" and no Stop (EA-4) |

Reached only by acting in a sample: `approved` (Confirm → "Checking the outcome", Stop still available), `rejected` (Reject proposal), `stopped` (Stop task; says what was in flight).

## How Stop is shown in every state (AG-CTRL-1)

Under the composer, a stop slot shows the latest run's status and **Stop task**. It is enabled whenever the latest run is active (reply pending, clarification, running, waiting approval, verifying), and also sits on the active run card. When nothing runs (empty, ended runs, legacy, the gallery's ended states) the control stays in place, disabled, with the visible reason "Nothing is running", so it is never enabled and then failing (AG-ENT-1). In "Result not confirmed" it is disabled with "Stopping is unavailable while the result is unconfirmed" and the safe check is offered instead (EA-4).

## Surfaces covered and not covered

Covered: Workspace (full page) at 320, 390, 768 and 1440 px and in landscape, and Docked (an embedded 26 rem panel beside a sample host page). Compact (overlay) and Workbench were not rendered separately: they are narrow and wide placements of the same composition, and the layout switches on the app's own width (container queries), so the docked and phone renders stand in for them. This is recorded as a limit in the QA file.

## Reused and changed

| Source | Used as | Changed here |
|---|---|---|
| `ui/packages/tokens/src/generated/tokens.css` | Linked stylesheet (light, dark, high contrast) | Nothing |
| `ui/packages/components/src/primitives/brand/e-agent-mark.svg` (owner logo) | Linked image | Nothing |
| `ui/packages/ui-core/src/i18n.ts` strings | Copied EN and VI text for status, approval, composer and disclosure copy | Nothing; copied strings keep their product wording |
| `ui/packages/components/src/primitives/primitives.css` | Button and badge roles mirrored in `styles.css` from tokens | Nothing |
| `../agentic-chat-v4/` (study 04) | Composition (conversation first, closable workspace, phone view switch) and the verify approach | Nothing |

## Files

`index.html`, `styles.css`, `app.js` (rendering and the labelled prototype transitions), `scenario.js` (the sample thread), `strings.js` (EN and VI), `compare.html`, `verify.mjs`, `QA.md`, `screenshots/`.

## Sample data

Every product, supplier, order number, person, time and result is fictional and labelled as a sample in the interface ("Sample data" in the header, "(sample)" on records). Nothing calls a model, a server or a network: the thread is built from fixed sample records, and sending a message moves to the next sample state.
