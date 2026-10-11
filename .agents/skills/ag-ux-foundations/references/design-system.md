# Design-system requirements

A candidate design system is adopted only if it meets these requirements. Each criterion uses the format described in `standard.md`; source IDs, tiers and reading levels are defined in `sources.md`.

### AG-DS-1 — Semantic tokens

- **Statement:** Visual values (colour, spacing, size, type, duration) are defined as semantic design tokens in the Design Tokens Community Group format, and components reference tokens; components contain no literal colour values.
- **Sources:** S-17 (3.8 Alias (Reference); 8 Types), S-11 (Style elements: new colour and style tokens for AI)
- **Enforcement:** gate, test
- **Max severity:** High
- **Evidence:** The token source files validated against the format; a lint or search result showing no literal colour values in component styles; the token that backs each AI-specific style.
- **Notes:** S-17 defines aliases (a token whose value references another token, so a role name can point to a palette value) and typed tokens; it is a Candidate Recommendation from a community group, not a W3C Standard. Naming tokens by role is a practice built on aliases, not a rule in S-17. S-11 shows a design system shipping dedicated tokens for AI styling inside its main themes.

### AG-DS-2 — Verified themes

- **Statement:** Every theme the design system offers, including light, dark and high-contrast, is verified for text contrast and for the non-text contrast of interface components and their states (including the focus indicator), and the verification is repeated for each theme.
- **Sources:** S-01 (SC 1.4.3 Contrast (Minimum); SC 1.4.11 Non-text Contrast; Conformance 5.2.2 Full pages)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Per-theme contrast report for text pairs and for component boundaries, state indicators and focus indicators, against 4.5:1 for text and 3:1 for non-text.
- **Notes:** SC 1.4.3 sets 4.5:1 for text (3:1 for large text) and SC 1.4.11 sets 3:1 for visual information required to identify components and states. The focus indicator is such visual information when it identifies the focused state. WCAG does not require a dark or high-contrast theme; where a theme is offered it is part of the content as presented and must conform.

### AG-DS-3 — Density without losing target size

- **Statement:** Where the design system offers a density scale, every density, including the most compact, keeps pointer targets at least 24 by 24 CSS pixels or meets one of the exceptions in SC 2.5.8.
- **Sources:** S-01 (SC 2.5.8 Target Size (Minimum)), S-14 (Design systems: components designed for dense information)
- **Enforcement:** test
- **Max severity:** Blocker
- **Evidence:** Measured target sizes for each interactive component at each density, with the exception relied on (spacing, equivalent control, inline, user agent, essential) where a target is smaller.
- **Notes:** S-01 gives the 24 by 24 CSS pixel minimum and its exceptions. S-14 supports only the general point that enterprise design systems are built for dense information; offering a density scale is a design choice, not a sourced requirement.

### AG-DS-4 — AI-origin treatment is scoped

- **Statement:** The AI identity treatment (label, colour, glow or equivalent) is applied to AI-originated elements, and not to verified facts, system records or decision terms.
- **Sources:** S-11 (Style elements; AI label: use the AI label and styling to mark instances of AI usage), S-04 (Art. 50(2))
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Screenshots of a screen mixing AI-originated and system-of-record content, showing which elements carry the AI treatment, and a token-usage list for the AI styles.
- **Notes:** S-11 says to use the AI label and styling to mark instances of AI usage, and that a consistent identity builds awareness of AI presence; S-04 (50(2)) requires AI-generated synthetic content to be marked in a machine-readable format and detectable as artificially generated. Neither source says the treatment must be withheld from other content. That limit follows from the purpose of marking: styling applied to verified facts or decision terms would misstate their origin.

### AG-DS-5 — Status never conveyed by colour alone

- **Statement:** Status and severity are never conveyed by colour alone: every status and severity level also carries text, an icon, or both.
- **Sources:** S-01 (SC 1.4.1 Use of Color)
- **Enforcement:** test, review
- **Max severity:** Blocker
- **Evidence:** Grayscale or colour-blind-simulated screenshots of every status and severity level showing each is still distinguishable; accessibility-tree output showing the text alternative.
- **Notes:** SC 1.4.1 says colour is not used as the only visual means of conveying information, indicating an action, prompting a response or distinguishing a visual element. See also AG-A11Y-4.

### AG-DS-6 — Motion with reduced alternatives

- **Statement:** Motion durations and easings are tokens; motion triggered by interaction can be disabled through a reduced-motion alternative; no essential information is conveyed only by animation.
- **Sources:** S-01 (SC 2.3.3 Animation from Interactions), S-17 (8.5 Duration)
- **Enforcement:** test
- **Max severity:** High
- **Evidence:** Test run with the reduced-motion preference on, showing each animation removed or replaced; list of motion tokens.
- **Notes:** SC 2.3.3 is Level AAA, so this criterion is capped at High rather than Blocker. S-17 defines a duration token type. The rule on essential information follows from the essential exception in SC 2.3.3 and is a design inference. See also AG-A11Y-1 for automatic motion that lasts more than five seconds (SC 2.2.2 Pause, Stop, Hide, Level A, part of AA conformance).

### AG-DS-7 — Consistent status scale

- **Statement:** Each status and severity level has one icon, label and colour treatment on one ordered scale, used identically wherever that level appears.
- **Sources:** S-01 (SC 3.2.4 Consistent Identification)
- **Enforcement:** review
- **Max severity:** High
- **Evidence:** Inventory of every place each status or severity level is rendered, with the icon and label used in each.
- **Notes:** SC 3.2.4 requires components that have the same functionality within a set of pages to be identified consistently. Reading a status indicator as such a component, and requiring an ordered scale, is an interpretation of that criterion.
