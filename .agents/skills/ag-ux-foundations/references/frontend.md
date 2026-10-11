# Frontend standard

This file separates durable rules from volatile choices. Durable rules (`AG-FE-*`) change rarely and only with owner approval. Stack decisions and the trends backlog change often and are reviewed on a schedule. Criteria use the format described in `standard.md`; source IDs, tiers and reading levels are defined in `sources.md`.

## Durable rules

### AG-FE-1 — Server authority

- **Statement:** Client state can never grant permission or record an approval; permission and approval status shown to the user come from authoritative server records, and no interaction approves implicitly.
- **Sources:** S-06 (ASI03: Prevention 3, Mandate Per-Action Authorization; Common Example 4, TOCTOU; ASI09: Common Example 2, Missing Confirmation for Sensitive Actions; Common Example 6, consent laundering through read-only previews)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Test that edits client state (store, storage, URL, response copy) to claim a permission or approval and shows the server rejects it and the UI reflects the server record; test that opening, previewing or focusing a decision surface triggers no approval.
- **Notes:** ASI03 recommends re-verifying each privileged step with a centralized policy engine and warns that permissions checked at one time can be stale at execution. ASI09 lists missing confirmation and previews with side effects as ways user trust becomes execution. Treating the browser as an untrusted client follows from these.

### AG-FE-2 — One owner per state

- **Statement:** Each piece of state has one owner; values that can be computed from existing state or props are computed, not mirrored into a second store.
- **Sources:** S-20 (Principles: avoid redundant state; avoid duplication in state)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** State inventory naming one owner per item, and a list of derived values with where each is computed.

### AG-FE-3 — Typed wire contracts

- **Statement:** Client types for server data are generated from the API's schema description, not written by hand, and a schema change that breaks the client fails the build.
- **Sources:** S-18 (4.8.24 Schema Object)
- **Enforcement:** gate, test
- **Max severity:** High
- **Evidence:** Build log showing type generation from the schema and a failing build after an incompatible schema change.
- **Notes:** S-18 defines the Schema Object as the definition of input and output data types for an API, a superset of JSON Schema. That generation is automated and a break fails the build is an engineering practice, not stated in S-18.

### AG-FE-4 — Exclusive UI states

- **Statement:** Mutually exclusive UI states are modelled as one discriminated union (or equivalent), so contradictory combinations cannot be represented.
- **Sources:** S-20 (Principles: avoid contradictions in state), S-07 (self-descriptiveness; catalogue and abstract only)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** The type or state definition for each exclusive group, and a note that no two flags in the group can both be true.
- **Notes:** S-20 states that state structured so pieces may contradict each other leaves room for mistakes. S-07 was available only as a summary and does not carry this criterion.

### AG-FE-5 — Accessible primitives

- **Statement:** Interactive primitives (dialog, tabs, listbox, menu button, disclosure) implement the APG pattern for their role, through a conformant library or with equivalent keyboard and role tests.
- **Sources:** S-02 (Patterns: Dialog (Modal), Tabs, Listbox, Menu Button, Disclosure; keyboard interaction and roles sections)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** For each primitive, the APG pattern it follows and a passing test of its keyboard interaction and roles.
- **Notes:** Only the five pattern pages listed in `sources.md` were read; for other patterns the relevant pattern page is read before the criterion is applied. See also AG-A11Y-2.

### AG-FE-6 — Container-relative layout

- **Statement:** Layout responds to the width of its container, not only the viewport, so narrow embedded placements reflow without loss of content or functionality or two-dimensional scrolling.
- **Sources:** S-01 (SC 1.4.10 Reflow; Conformance 5.2.2 Full pages, Note 3), S-16 (Baseline 2023 features: size container queries)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Screenshots of the surface in containers at widths down to the equivalent of 320 CSS pixels with no horizontal scrolling, in a standalone page and in an embedded placement.
- **Notes:** SC 1.4.10 sets the 320 CSS pixel width as a viewport requirement and says each responsive variation of a page must conform. Applying it to an embedded container is an extension for surfaces placed in host pages. S-16 lists size container queries among the Baseline 2023 features that reached Newly available; current status is checked under the update process.

### AG-FE-7 — Embedding focus isolation

- **Statement:** An embedded surface keeps focus handling inside its own boundary: opening an overlay or dialog moves focus into it, Tab and Shift+Tab stay inside while it is modal, content under a modal is inert, and closing returns focus to the invoking control without stealing focus from the host page.
- **Sources:** S-02 (Dialog (Modal) pattern: About this pattern; Keyboard Interaction)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Browser test inside a host page with its own focusable elements, recording the focus order on open, Tab cycling, Escape and close.
- **Notes:** S-02 supports the focus behaviour: windows under a modal dialog are inert, Tab does not leave the dialog and focus moves to an element inside the dialog on open. Style isolation, overlay placement inside the surface's boundary, and independence from host-page globals are further expectations for embedding that no source read here covers; they belong in the embedding test and are not claimed as sourced.

### AG-FE-8 — Baseline adoption

- **Statement:** CSS and DOM features are used when Baseline Widely available; a Newly available feature is used only with a tested fallback; a feature with Limited availability is used only by recorded decision.
- **Sources:** S-16 (How do things become Baseline? Newly available, Widely available, Limited availability)
- **Enforcement:** review
- **Max severity:** Medium
- **Evidence:** For each non-trivial feature in use, its Baseline status at the review date; the fallback test for each Newly available feature; the decision record for each Limited availability feature.
- **Notes:** S-16 defines Newly available as supported by all core browsers, Widely available as 30 months after that date, and Limited availability as not yet supported across core browsers. The adoption rule itself is a policy layered on those definitions, chosen because the surface can be embedded in host pages the owner does not control.

### AG-FE-9 — Test strategy

- **Statement:** Behaviour is covered by unit, component and browser tests; automated accessibility checks run on every state, theme and responsive variation shown, and complete processes are checked by a human before release.
- **Sources:** S-01 (Conformance 5.2.2 Full pages, Note 3; 5.2.3 Complete processes), S-02 (Patterns: keyboard interaction and roles sections)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Test inventory by level, the accessibility check configuration with its matrix of states, themes and widths, and the release checklist with the human check recorded.
- **Notes:** S-01 says conformance is for full pages including each automatically presented variation, and that every page in a process must conform. The mix of test levels, and the need for human checks beyond automated ones, are engineering practice not stated in the sources read.

### AG-FE-10 — No sensitive client persistence

- **Statement:** No secrets, task text or other sensitive data appear in URLs, browser storage or client telemetry; credentials are short-lived and scoped, and client-side context does not outlive the session it belongs to.
- **Sources:** S-06 (ASI03: Common Example 2, Memory-Based Privilege Retention and Data Leakage; Prevention 1, Task-Scoped, Time-Bound Permissions; Prevention 2, Isolate Agent Identities and Contexts)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Inspection of URLs, local and session storage, IndexedDB, cookies and outgoing telemetry payloads after a representative task, showing none contains secrets or task text.
- **Notes:** ASI03 concerns agents that cache credentials or retrieved data and leak them across tasks or users, and recommends short-lived scoped tokens and per-session isolation. Applying this to URLs, browser storage and telemetry is an extension of that reasoning, not a statement in the source. See also AG-ID-4.

### AG-FE-11 — Responsiveness budget

- **Statement:** Interaction responsiveness is measured against INP thresholds in the field, including while a response is streaming; INP at or below 200 ms at the 75th percentile is good and above 500 ms is poor.
- **Sources:** S-19 (What is a good INP score)
- **Enforcement:** test
- **Max severity:** Medium
- **Evidence:** Field or lab INP measurements for the main interactions, with and without a streaming response, and the percentile used.
- **Notes:** The thresholds are from S-19. Including streaming follows from INP measuring the latency of interactions on the page during use. Optimisation work follows measurement, not the reverse.

### AG-FE-12 — Verified status comes from the server

- **Statement:** The client never promotes a result to verified, and a verified or unverified marker is rendered only from a server-provided field.
- **Sources:** S-06 (ASI09: Prevention 5, Adaptive Trust Calibration: cues such as "unverified source")
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Test in which the client holds an unverified result and the response omits the verified field, showing the result renders as unverified.
- **Notes:** ASI09 recommends visual cues such as "unverified source" to reduce blind approval. That the marker be server-derived is a design consequence of AG-FE-1 and is not stated in ASI09. See also AG-APPR-6.

### AG-FE-13 — Unknown shapes fail visibly

- **Statement:** Unknown or malformed response shapes and missing values produce an explicit unsupported or unknown state, never a default of empty, zero or granted.
- **Sources:** S-18 (4.8.24 Schema Object: behaviour left to the application), S-06 (ASI03: Prevention 3, Mandate Per-Action Authorization)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Contract tests that feed unknown enum values, missing fields and wrong types, showing the rendered unsupported state, and a check that no code path defaults a missing permission to granted.
- **Notes:** S-18 says that where JSON Schema leaves behaviour to the application, the application consuming the document defines the semantics, so handling of unlisted shapes is the client's responsibility. The explicit unsupported state is a design requirement on top of that. See also AG-UNC-4.

## Stack decisions

Each product records its current choices in its binding-requirements reference. This table lists the decisions a frontend must make, the standard each is judged against and when to revisit it. The lockfile is the authority on versions; none are recorded here.

| Decision | Current choice | Standard followed | Revisit trigger | Upstream to watch |
|---|---|---|---|---|
| Component accessibility library | see the consuming product's binding requirements | AG-FE-5, AG-FE-7 | Major version of the library; a pattern it does not cover | The library's release notes and the APG |
| Styling approach | see the consuming product's binding requirements | AG-FE-6, AG-FE-8, AG-DS-1 | Baseline status change for a feature in use; embedding isolation failure | Baseline status for CSS features |
| Token pipeline | see the consuming product's binding requirements | AG-DS-1, AG-DS-6 | Major version of the compiler; format revision | The Design Tokens Community Group format |
| State store | see the consuming product's binding requirements | AG-FE-1, AG-FE-2, AG-FE-4 | Major version of the store; a state-ownership violation found in review | The store's and the UI framework's release notes |
| Routing | see the consuming product's binding requirements | AG-FE-1, AG-FE-10 | Major version of the router; sensitive data found in URLs | The router's release notes |
| Component gallery | see the consuming product's binding requirements | AG-FE-9, AG-DS-2 | Major version; loss of per-theme or per-state coverage | The gallery tool's release notes |
| Test runner | see the consuming product's binding requirements | AG-FE-9, AG-FE-11 | Major version; browser coverage gap | The runner's release notes |

## Update process

Last reviewed: 2026-10-11

- Review this file when a listed dependency has a major version, when the Baseline status of a trends-backlog item changes, and at least every 6 months.
- Verify every claim against official release notes or current documentation, not memory.
- Record the review date above.
- A change to a durable rule needs owner approval, and a recorded decision where the change is material.

## Trends backlog

These are items to evaluate. Listing an item implies no decision.

### CSS container queries

- **Question:** Can size container queries replace viewport and resize-observer based layout for embedded placements?
- **Evaluate by:** Prototype a narrow embedded placement and test reflow against AG-FE-6 in the supported browsers.
- **Baseline status (verify):** S-16 lists size container queries as Newly available in February 2023; confirm the current status.

### React Compiler

- **Question:** Does automatic memoisation improve measured responsiveness without changing behaviour?
- **Evaluate by:** Compare INP on the main interactions with and without it (AG-FE-11), and run the full test suite.
- **Baseline status (verify):** Not a web platform feature; check the framework's release notes for its stability status.

### `popover` and anchor positioning inside a shadow root

- **Question:** Do the `popover` attribute and anchor positioning work for overlays inside an embedded shadow root, with correct focus and layering?
- **Evaluate by:** Embedding test with a host page, checking focus behaviour against AG-FE-7 and fallback behaviour against AG-FE-8.
- **Baseline status (verify):** Check each feature separately; they may differ.

### View Transitions with reduced motion

- **Question:** Can view transitions be used while honouring the reduced-motion preference and without hiding state changes?
- **Evaluate by:** Test each transition with the reduced-motion preference on (AG-DS-6) and confirm no information depends on the animation.
- **Baseline status (verify):** Check same-document and cross-document transitions separately.
