# Agentic overlay: trend research and interactive design study

Date: 2026-10-08. Status: candidate design and isolated synthetic prototype. Builds on [research 12](12-agentic-overlay-ux-research.md); preserves that report. No accepted architecture decision or product release status changes.

## Deliverables and how to run

- [Interactive mockup](../archive/research/mockups/agentic-overlay/index.html): three appearance candidates using the same procurement fixture; floating, docked and expanded placement; responsive mobile layout.
- [Visual reference board](../archive/research/mockups/agentic-overlay/board.html): comparable candidate compositions and eight annotated pattern studies with source links. These are original schematics, not reproduced vendor screenshots.
- [Prototype source](../archive/research/mockups/agentic-overlay/app.js) and [style system](../archive/research/mockups/agentic-overlay/styles.css).

From the repository root:

```bash
python3 -m http.server 4178 --bind 127.0.0.1 --directory research/mockups/agentic-overlay
```

Open `http://127.0.0.1:4178`. The HTML also works directly from disk. There is no build step, external asset request, backend connection, live business data or actual authorization. State stays in memory for the current page. Reload starts the review scene again.

## Research: directions and limits

The following are observed patterns in primary vendor guidance and protocol documentation, not measured market adoption or comparative usability evidence. Sources were consulted on 2026-10-08. Recommendations in the last column are project-specific inferences.

| Pattern | Primary source and observation | Application to this study |
|---|---|---|
| Persistent, contextual assistance | [Microsoft Agent UX](https://microsoft.design/articles/ux-design-for-agents/) frames agents around space, continuity and human control, including uncertainty. Some guidance is forward-looking. | Quiet host workspace, persistent launcher, meaningful state badge and recoverable task surface. |
| Artifact-centered business work | [SAP’s autonomous enterprise design](https://www.sap.com/design/stories-resources/designing-the-autonomous-enterprise) presents Joule Work as an intent-driven, adaptive workspace. Product imagery is a design example, not a guarantee of general availability or applicability. | A draft purchase order takes priority over a transcript or field grid; expansion gives evidence more room. |
| Recognizable AI with progressive explanation | [Carbon for AI](https://www.carbondesignsystem.com/building-blocks/foundations/carbon-for-ai) uses AI identity and contextual explanations; styling should identify AI rather than decorate unrelated elements. | Restrict expressive light treatment to identity/composer in the AI Presence candidate. Keep currency, exact terms and approval controls plain. |
| Interaction protocols separate from rendering | [AG-UI overview](https://docs.ag-ui.com/introduction) describes event-oriented interaction, state synchronization and human intervention. | Track as a potential event adapter, preserving the existing authoritative run contract. |
| Constrained declarative interfaces | [A2UI](https://a2ui.org/) describes client-rendered component declarations from an approved catalog. The page consulted lists v0.9.1 as current and v1.0 as candidate; this differs from older preview wording in existing research. | Consider only for future non-authoritative artifacts. Catalog constraints do not replace data validation, authorization, safe link handling or approval policy. |

## Technology recommendation

The existing repository already has the appropriate implementation foundation. A new agent framework is not required to realize this visual design.

| Technology | Role and recommendation | Boundary |
|---|---|---|
| React + TypeScript + Vite | Retain the declared workspace versions for product implementation; compose artifacts and state views from typed projections. | This research prototype uses dependency-free HTML/CSS/JS for quick visual review; it is not a replacement UI implementation. |
| React Aria Components | Retain accessible dialog, press and focus behavior. [Official quality guidance](https://react-aria.adobe.com/quality) covers keyboard, touch and internationalization behavior. | A library does not certify accessibility; verify keyboard, zoom, contrast and screen reader behavior in the integrated UI. |
| Existing DTCG tokens / CSS variables | Map candidate values into the existing token compiler after visual selection. Use semantic state tokens consistently across appearances. | Inline prototype variables are exploratory; do not copy hard-coded styles into shared production components. |
| Existing ui-core + typed client + SSE | Reuse host snapshots, revision checks, stream recovery and approval state machine per accepted ADRs 0007, 0011, 0015 and 0016. | No model text may set committed/verified state or synthesize missing readable source facts. |
| Custom element / Shadow DOM | Retain the existing embedding boundary and scoped style surface. | This mockup uses a simulated host in one document; it does not test embedding isolation. |
| AG-UI | Optional future protocol adapter. | Not the action ledger, approval model or canonical stream. No dependency added. |
| A2UI | Research candidate for future declarative, allowlisted artifacts. | Out of MVP scope; never generate approval or policy surfaces from agent instructions. No dependency added. |

## Candidate system

**Calm enterprise** is the recommended starting hypothesis: warm surrounding canvas, white working surface, charcoal content and restrained indigo action. **AI Presence** adds localized light effects and editorial serif headings. **Dense operator** uses graphite surfaces, tighter spacing and expanded evidence. The fixture, approval boundary and outcome semantics are identical across all three.

The default overlay is 510px wide with a flexible, independently scrolling body and anchored decision footer. Expanded mode caps at 850px and places the artifact beside evidence. Docked mode attaches to the viewport edge. Below 760px, every mode uses a near-full-width sheet with the same decision controls.

Typography: system sans for controls, terms and amounts; Georgia for optional editorial headings. No remote fonts. Spacing is based on 4px increments; artifact radius 11px, overlay radius 18px. The primary palette is canvas `#F5F4F0`, surface `#FFFFFF`, ink `#262936`, action `#5555D9`, verified `#26765E`, attention `#95601C`. Small host labels are intentionally background scenery; interactive production labels need normal contrast and sizing checks when promoted.

The appearance button controls **appearance** and **placement** in separate groups. The bottom Design Studio controls are prototype tools, not proposed product chrome. Switching retains scenario, intent, composer draft and disclosure state, issues no action and closes any pending confirmation. Minimize retains the task and restores focus to the launcher. Escape first dismisses confirmation or appearance settings, then minimizes from the overlay.

## Interaction and content contract

| Scene | Prototype behavior | Product data/behavior required |
|---|---|---|
| Ready | Capability statement, bounded examples, editable request | Admitted task metadata and authorized context, with availability limits |
| Working | Recorded fixture milestones; explicit manual preview advance | Actual run events, no fabricated progress percentage, ETA or private reasoning |
| Clarification | One warehouse question, original request retained | Host-owned clarification projection and authorized answer submission |
| Review | Business summary, full fixture terms, source evidence, decline or review-and-approve | Complete `ApprovalPresentation`, current revisions, digest validation and rule findings |
| Confirmation | Native modal, summary/scope and explicit second click; heading receives focus | ui-core confirmation state; exact server-bound command and mandatory revalidation |
| Approved/executing | Approval recorded; no claim of committed effect | Durable admission/dispatch events |
| Committed/verifying | Creation receipt distinguished from completed verification | COMMITTED receipt and independent read-back status |
| Unknown | Possible committed write explained; status check remains unresolved | Authorized reconciliation; no blind replay |
| Verified | Synthetic record reference, matched fields and explicit remaining draft status | Authoritative correlated receipt and verifier report |
| Stale | Approval absent; refresh returns to review fixture | Actual revised proposal must be revalidated and reviewed |
| Declined/stopped | No submission in the fixture | Authoritative rejection/cancellation result and truthful effect status |

The fixture assumes demand 400, stock 160, shortage 240, an approved supplier offering USD 4.50/unit, zero tax, a USD 1,200 budget and delivery by 2026-10-16. Names, source revisions, rule findings, timestamps and PO reference are authored design data. They are not captured model or ERP evidence. The mockup does not perform a JCS digest check and must not be mounted as a real approval component.

The exact fixture terms intentionally disclose this limitation. Production must render the complete canonical proposal and connection scope from the existing contract, showing explicit unknowns when labels or facts are unavailable. A pretty proposal summary is never sufficient authorization.

## Evaluation plan

Use a small formative study with procurement users before selecting a direction; compare all three on the same scenario and alternate presentation order. Ask participants to delegate the shortage task, explain the supplier/amount/date/effect, inspect its sources, decline once, approve once, minimize and restore, switch appearance and handle an unknown outcome. Record decision errors, overlooked limits, evidence discoverability, intervention success and subjective workload. Include keyboard use, 200% zoom and narrow screens.

Success criteria are design targets, not observed results: users correctly identify draft-only scope, distinguish approval/commit/verification, and choose a status check rather than another write after uncertainty. Automated interaction checks establish mechanics only. No human usability study, assistive-technology certification or live integration qualification is claimed.

## Verification

See [prototype QA notes](../archive/research/mockups/agentic-overlay/QA.md) for actual checks and retained screenshots. Product integration, localization, actual host projections and live human-approved sandbox qualification remain outside this mockup.
