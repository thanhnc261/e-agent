I read `AGENTS.md`, all eight mockup files, `research/15-agentic-ux-patterns-mockup.md`, the relevant parts of `research/14`, and nine screenshots (01, 03, 04, 06, 08, 09, 11, 13, 14, 15-320, 15-390, 16-320, 17-320, 18-390). I did not run the prototype or `verify.mjs`; I audited the script statically.

# Design study 03 — review

## Verdict

**Ready for owner design review: yes, after B1–B3 below.** The structure, state taxonomy and honesty framing are the strongest of the three studies, and the walkthrough in `design-notes.html:344-369` works as a demo script. But each blocker shows the owner a contradiction inside the exact story the study is selling (exact-action approval), so fixing them is cheap insurance for the walkthrough.

**Ready for production: no**, and the study correctly does not claim it (`README.md:38`, `QA.md:31-35`, `design-notes.html:372-386`, `research/15-agentic-ux-patterns-mockup.md:32-36`). Nothing here is applied to the product.

Credit where due: the missing-access scenario (`app.js:177`), the unknown-outcome/no-resend treatment (`app.js:183`, `app.js:226-227`), the stale-revision block (`app.js:184-185`, `app.js:228-229`), `Health: Simulated configuration; not probed` (`app.js:120`), and the composer that refuses to pretend it understands free text (`app.js:417-429`) are all honest in the way `AGENTS.md:29-38` requires. The seven pattern slugs cited in `design-notes.html:229-323` all exist in the live library index — citations check out (I verified the index listing, not each page's content).

---

## Blockers (fix before the owner walkthrough)

**B1 — The material terms are below the fold while the approve button is always visible; `design-notes.html` claims the opposite.**
`design-notes.html:252-254` states the guardrail "Warnings, audience, destination, and decision remain visible." In the default compact review at 1440×1100 (`screenshots/03-compact-review.png`) and even expanded (`screenshots/04-expanded-review.png`), *none* of the four terms (Customer, Project owner, Target kickoff, Visibility) nor the green scope line are visible — the body is cut mid-term-row — while `Review & approve` sits in the pinned footer. `screenshots/14-dark-review.png` is worse: the purchase draft shows Total but clips Tax and Delivery. Cause: `artifact()` places `.terms` and `.scope-line` *after* the document preview (`app.js:195-210`) inside the single scrolling `.agent-body` (`styles.css:930-941`), while `.agent-footer` is `flex-shrink: 0` (`styles.css:1263-1272`). `QA.md:29` acknowledges the scroll but frames it as intentional; that is a reasonable layout choice and a wrong default for an approval surface.
*Impact:* the reviewer can approve a purchase without the price ever having been on screen. It also makes the study's central claim unverifiable by inspection.
*Remedy (pick one, cheapest first):* move `.scope-line` + `.terms` above `.document-preview` in `app.js:195`; or render the full term list inside the confirmation dialog (`app.js:264-268`), which also fixes H1; or gate the primary on the artifact having been scrolled to its end.

**B2 — The clarified audience is not carried into action 2, producing contradictory audiences on one screen.**
`app.js:196-201` hardcodes `["Audience", "8 internal members"]` for the message action, and the substitution at `app.js:206` only applies to the key `"Visibility"`. The scope line at `app.js:210` *does* use `state.clarification`. So after choosing "Project owner only" in the clarification flow (`app.js:181`, `app.js:431-435`), the action-2 review shows `Audience: 8 internal members` in the terms and `Project owner only · approval applies to this action only` in the scope line, and the confirmation dialog hardcodes `8 internal members` again (`app.js:266`). `verify.mjs:117-122` asserts only the `.scope-line`, so the contradiction passes the suite.
*Impact:* the one flow that demonstrates "we don't guess the audience" demonstrates two different audiences for the same action.
*Remedy:* derive the step-2 field list from `state.clarification` (single source), and build the confirm-dialog summary from the same field array rather than literals.

**B3 — "Inspect verification evidence" opens the input sources, not verification evidence.**
On the verified screen, `app.js:191` renders `Inspect verification evidence`, and `data-action="evidence"` (`app.js:398-404`) opens a dialog titled "Sources and verification" containing `sources(active())` — the same three input excerpts shown by `N sources · inspect context` at `app.js:192`. There is no read-back record, observed field values, read-back time or verifying identity.
*Impact:* the affordance promises exactly the independent-read-back evidence that `AGENTS.md:36` makes the distinguishing claim, and delivers the pre-action context instead. That is the kind of unsupported guarantee the review brief asks to flag, and it is worse than having no button.
*Remedy:* either rename to `Inspect sources` (one word, zero risk), or add a fixture read-back record — observed destination, observed audience, observed document ID, read-back timestamp, acting identity — in a distinct dialog.

---

## High priority (fix before any adoption into the product)

**H1 — The confirmation dialog binds less than revision 2 did.** `app.js:264-268` shows artifact title, scope and revision. `research/14-enterprise-wide-agent-experience.md:72` specifies "operation, content, destination, audience, acting identity, connection version, workspace and proposal revision." Destination, acting identity and connection version appear only inside a collapsed `<details>` on the review screen (`app.js:210`) and nowhere in the confirmation. *Remedy:* render the same normalized-action block in the dialog as in the review, from one function.

**H2 — A dispatched action is still labelled `Draft` / `ACTION 2 OF 2`.** In the unknown-outcome state (`screenshots/09-unknown-outcome.png`, `18-unknown-390.png`) the artifact is passed `muted=true` (`app.js:183`) but `app.js:195` still renders the `Draft` mini-label and the proposal eyebrow for something that was already sent and may have committed. *Remedy:* add a dispatched/unresolved label variant; `Draft` must never appear after dispatch.

**H3 — Topbar text collides at 320px.** `screenshots/15-home-320.png` shows the `Interactive concept` badge overlapping the breadcrumb "Overview". `.topbar` is fixed at `height: 44px` with `justify-content: space-between` (`styles.css:1707-1710`) and `.topbar > div` has no `min-width: 0` or truncation (`styles.css:374-378`), so the breadcrumb overflows into its neighbour. 390px is clean. *Remedy:* `min-height` instead of `height`, `min-width: 0; overflow: hidden; text-overflow: ellipsis` on the breadcrumb, and drop the "Workspace /" prefix below 360px. Note this defect passed the suite — see evidence limits.

**H4 — Approval-scope text rendered at 7px on mobile.** `styles.css:1892-1894` sets `.artifact-top .eyebrow { font-size: 7px }`. That eyebrow carries `ACTION 1 OF 2 · DOCUMENT · V1` (`app.js:195`) — the sequencing label that communicates "this approval covers only the first of two effects" (`screenshots/16-review-320.png`). *Remedy:* floor at 10px and let it wrap; shorten to `ACTION 1 OF 2 · V1` on narrow widths.

**H5 — Simulated states leak handoff-specific copy into other scenarios.** `app.js:180-181` renders "Who should have access? The project team and the wider delivery group have different access…" for *any* scenario selected in the study bar — including the purchase draft, where the clarification then rewrites the purchasing scope line to "Delivery team only". *Remedy:* move clarify/working copy into `fixtures.js` per scenario, or restrict the state selector to the scenarios each state is authored for.

**H6 — The context rail is not state-aware.** `app.js:221` always renders "Create the document first. Posting the message needs its own approval." It is still there on the verified screen after both actions completed (`screenshots/08-verified.png`). *Remedy:* branch the boundary copy on `state.scene`/`state.step`.

**H7 — Assistant semantics and announcements.** `#agent` is `role="dialog"` with no `aria-modal`, no focus containment and no scroll lock (`index.html:79-85`); the page behind stays interactive, so clicking a task card behind the panel silently replaces the open task (`app.js:283-291`). Separately, `announce()` sets the live region to the bare status label (`app.js:173`), re-set identically on every render — many screen readers will not re-announce an unchanged string, and "Verified" alone does not convey what was verified. *Remedy:* use `role="complementary"` + `aria-label` for the non-modal panel (or make it genuinely modal when expanded), and announce a composed sentence including task name and the state change.

**H8 — Unmodified `n` shortcut fires while reviewing.** `app.js:457-466` triggers "New task" on any bare `n` outside form fields, including when focus is on a footer button mid-review; it minimizes the current task and moves focus to the composer. The task is recoverable via the launcher, so this is disruptive rather than destructive. *Remedy:* ignore the key while `#agent` contains focus, or require a modifier.

**H9 — Cross-enterprise framing has one requester-approver identity.** Jamie Lee requests and approves (`index.html:54-57`, `app.js:210`). There is no approver queue, delegation, escalation or second-party review anywhere in the six scenarios. `QA.md:33` flags the role model as unevaluated, which is honest, but this is the largest conceptual gap for an "enterprise-wide" claim, and the pattern library the study cites has a page for exactly this (`/patterns/ui-ux-patterns/risk-tiered-approval-escalation`, confirmed present in the index) that the study does not use. *Remedy:* before adoption, sketch one state where the approver is not the requester — even a single pending-approval row addressed to someone else.

**H10 — Audience is represented by a member count.** `app.js:198` states `Audience: 8 internal members`. `research/14:74` explicitly warns "A channel-membership count alone is not a disclosure check" and notes revision 1's handoff fixture carried a cleared-for-audience statement. Study 03 dropped that line. *Remedy:* restore an explicit disclosure statement alongside the count.

---

## Polish

| # | Finding | Ref | Remedy |
|---|---|---|---|
| P1 | "across your enterprise.Bring the context" runs together on mobile — `<br>` is hidden with no space in the source | `styles.css:1729-1731` + `app.js:99`; `screenshots/15-home-390.png` | Split the two sentences into separate `<p>`/`<span>` elements |
| P2 | The fixed resume launcher covers page content (filters, first task card) with no reserved space | `styles.css:1304-1307`, `1951-1954`, `1703-1706`; `screenshots/15-home-{320,390}.png` | Add bottom padding to `.shell` when the launcher is shown, or dock it as a bar |
| P3 | Mobile touch targets below the 44px guideline (tabs ≈31px, filters ≈27px, panel icon buttons 28×32) | `styles.css:1030-1035`, `1779-1781`, `1859-1862` | Raise to ≥40px via padding; they clear the 24px WCAG minimum but are tight for thumb use |
| P4 | Hardcoded hex bypasses the token layer and does not re-theme in dark (primary button, composer border, avatar, category tile tints, notice border) | `styles.css:486-493`, `503`, `355-356`, `626-641`, `1414` | Fold into `:root`/`body.dark` variables — this matters for the component-extraction story |
| P5 | `Check existing result` stays enabled and is a no-op on repeat once `state.checked` is true | `app.js:226-227`, `384-388` | Swap to a terminal control ("Escalate to an operator") after the first check |
| P6 | Blocked scenario dead-ends at "View connections"; `research/14:62` proposed offering a general checklist or an access-request preview | `app.js:177`, `224-225` | Add the fallback offer |
| P7 | The missing-access scenario shows `People directory` as an ordinary context chip, indistinguishable from connected systems | `app.js:62`, `170` | Mark unavailable systems in `badges()` |
| P8 | The dialog's focus ring on the `tabindex="-1"` heading reads as a text input | `app.js:247-249`; `screenshots/06-confirmation.png` | Move initial focus to "Back to review", or restyle — do not simply remove the indicator |
| P9 | Study-bar language inside the proposed product component: "Preview state · use the study controls to continue" in the activity timeline | `app.js:216` | Move to the `.studio` layer, keeping the product surface clean |
| P10 | The state picker shows "Needs review" while the panel shows "Setup needed" for blocked scenarios | `app.js:139`, `168` | Add a blocked option or disable the picker for that scenario |
| P11 | Fixture strings are interpolated unescaped (`sources()`, summary/body/text in `artifact()`); only the composer draft is escaped | `app.js:195`, `213` vs `app.js:3-10` | Harmless with fixtures — record it as a do-not-port note, since `README.md:38` already warns against porting |
| P12 | `state.customPrompt` used but not declared in the initial state object | `app.js:42-56` vs `286` | Declare it |

---

## Suitability as a basis for reusable frontend components

**As a visual and behavioural specification: yes.** The nine-state task taxonomy, the artifact-plus-terms-plus-scope composition, the compact/expanded/minimized placements and the footer-as-decision-region are all directly transferable, and the token set in `:root` (`styles.css:1-27`) is close to a real palette once P4 is folded in.

**As a code basis: no**, which `README.md:38` already says. Concretely: rendering is `innerHTML` string concatenation into two roots (`app.js:169-171`); all interaction is one delegated click listener with a 20-branch if-chain (`app.js:275-406`); scenario-specific logic is baked into the generic renderer (`app.js:195` branches on `s.category === "Revenue"`, and the whole action-2 artifact is handoff literals); `styles.css` is a 2016-line flat global sheet with bare element selectors that would collide with the product's layer.

The one asset worth extracting before the code is discarded is **the state machine**, which currently exists only implicitly across `status()` (`app.js:138-151`), `taskContent()` (`app.js:175-192`), `footer()` (`app.js:223-241`) and the `<select>` in `index.html:129-137`. A table of nine states × permitted controls × status pill × footer copy, written down once, is the thing the product team can implement against and test; derived from `footer()` alone it is already an enforceable rule set ("no approve control exists in `unknown`, `stale`, `rejected`, `blocked` or read-only"), which maps cleanly onto the approval invariants in `AGENTS.md:32-36`.

---

## Evidence limits

I did not run the prototype or `verify.mjs`; the review is based on the source, `QA.md`'s reported pass, and the committed PNGs. Statements about rendering are grounded in the screenshots I opened, not in CSS reasoning alone — except the 650px `br` rule (P1), which I confirmed in both mobile screenshots.

Auditing what the script proves, assuming it passes as written:

- **Proven:** element counts and filtering (`verify.mjs:59-66`); the full approve → verify → second-approve → verified sequence advances state as designed (`:78-101`); no `data-action="approve"` control exists in unknown, stale or read-only states (`:108`, `:111`, `:132`); focus lands on `#modal-title` after approve and a subsequent Enter does not change the scene (`:79-84`); composer text reaches `.request` escaped and survives minimize/resume (`:167-174`); page-level `scrollWidth <= innerWidth` and footer-above-studio at 1440/390/320 (`:26-48`); `body` computed colour and background in dark (`:150-160`); zero page errors and zero non-localhost requests (`:195-196`).
- **Not proven, despite reasonable appearances:** nothing about overlap, clipping, truncation or contrast — H3's 320px collision is in a screenshot the suite captured and passed; nothing about whether decision-critical content is above the fold (B1); no tab-order, focus-containment or screen-reader checks (every interaction is a mouse click, so no flow is shown to be completable by keyboard alone); Enter-safety is proven only at the single moment after the dialog opens, not at other focus positions; dark mode is checked by two hardcoded `rgb()` equalities on `body` only, so no component-level dark contrast is covered, and the assertion will fail on any legitimate token change; touch-target sizes, reduced motion and `aria-live` output are untested. `QA.md:31-35` states these limits accurately — no usability, screen-reader, live-integration or role-model evidence is claimed anywhere, and none should be inferred.

One structural note: `verify.mjs:5-8` resolves `@playwright/test` through `../../../ui/package.json`, so the study is not self-contained and depends on the product UI workspace being installed. `README.md:42` documents this; it is fine for a study, worth remembering if the mockup outlives the current `ui/` layout.
