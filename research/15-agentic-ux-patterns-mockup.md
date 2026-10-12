# Agentic UX patterns: mockup before implementation

Date: 2026-10-09. Status: candidate design, pending owner review.

The owner requested a new mockup using the full [Agentic Design UI/UX pattern library](https://agentic-design.ai/patterns/ui-ux-patterns) and the previously supplied sources. Application work and Claude implementation are paused. The owner separately requested read-only Claude review of the completed mockup. This study preserves research 12–14 and both earlier mockup revisions.

## Deliverable

[Design study 03](mockups/agentic-workspace-v3/README.md) is a standalone interactive prototype. It contains a workspace, six fictional enterprise workflow examples, connection/access information, contextual launch inside a customer record, compact/expanded review, sources, clarification, separate approvals, and recovery states. The [visual rationale](mockups/agentic-workspace-v3/design-notes.html) maps the design to the references.

The direction is intentionally broader than procurement. It does not claim that the existing product implements all six domains or all illustrated integrations. All data and outcomes are labelled as samples.

The [identity and component catalog](mockups/agentic-workspace-v3/design-system.html) includes an original SVG logo, four variants, 27 matching icons, warm neutral/navy colors and reusable component examples. [Source coverage](mockups/agentic-workspace-v3/source-coverage.html) records text review of all 32 pattern pages and both articles. The pattern index and enterprise article were also visually inspected; not every interactive pattern demo was exercised.

## Reference use

- [Agentic Design pattern library](https://agentic-design.ai/patterns/ui-ux-patterns): visible autonomy boundaries, outcome states and recovery inform the overall flow. The study selectively applies human-in-the-loop, disclosure, activity, transparency, mixed initiative and ambient assistance; it does not attempt to include every pattern.
- [Chat Interface Patterns](https://agentic-design.ai/patterns/ui-ux-patterns/chat-interface-patterns): preserved context, rich artifacts and source inspection inform the task surface.
- [Agentic UX: 7 principles](https://medium.com/design-bootcamp/agentic-ux-7-principles-for-designing-systems-with-agents-019512c2caa9): contextual entry, familiar interactions and timely clarification inform the in-app flow.
- [Enterprise UX Design](https://uxpilot.ai/blogs/enterprise-ux-design): consistent navigation and reusable components inform the workspace. Role-specific behavior remains a research question.

These are practitioner design references, not comparative usability evidence. The detailed pattern-to-component mapping and links are in the visual rationale, avoiding another duplicate research report.

## Interaction decisions to evaluate

1. Start from an intent or an example workflow. Free text in this prototype selects no executable tool; reviewers choose a sample scenario explicitly.
2. Keep the proposed artifact central. Separate task conversation from source and activity inspection.
3. Review one exact action at a time. Creating a document and posting a message require separate approvals.
4. Show missing access and missing information explicitly. Do not silently guess the audience or fabricate a completed task.
5. Distinguish approval, verification and success. An unknown effect offers a read-back check and never a blind resend; an unresolved check remains unresolved.
6. Keep the same task during expansion and minimization. Mobile uses one scrolling body and an unobscured decision footer.
7. Use concise evidence-based explanations, not hidden reasoning, confidence percentages or simulated progress estimates.

## Adoption boundary

This mockup introduces no application contract or accepted ADR. If selected, map its composition into the existing token → primitive → feature → slot → layout architecture. The server remains authoritative for capabilities, connections, scope, exact action versions, approval and independent verification. Prototype fixture state must never be reused as enforcement logic.

Earlier application visual edits remain in the working tree and are paused; they are not the implementation of this new mockup and are not declared complete. The new files are under `research/mockups/agentic-workspace-v3/` only, plus this study/index documentation.

## Review evidence and limits

The repeatable browser script passes with no page errors or external requests. It captures desktop, 390px and 320px layouts and exercises approval separation, focus-safe confirmation, clarification, source inspection, rejection, stale/unknown states, escaped input and retained context. Screenshots were inspected; a wrapped brand and dark-theme foreground/background problem were corrected.

See [QA](mockups/agentic-workspace-v3/QA.md) for evidence and limitations. No live-system testing, screen-reader certification or measured usability improvement is claimed. Before adoption, have users explain what will change, which sources support it, who has access, and what “unknown outcome” means while performing the example tasks.
