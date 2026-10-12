# Visual rework: bring the implementation back to the mockup

**2026-10-10 owner correction:** Study 03 was rejected for its dashboard hierarchy, permanent sidebar and clutter. The current candidate is [study 04: conversation + workspace](../../research/mockups/agentic-chat-v4/README.md), with collapsible navigation and a right-side artifact workspace. Production work remains paused. A reviewer verdict on an earlier study is not owner acceptance.

**Paused by later owner direction (2026-10-09).** The owner requested a new mockup before further application changes. The current candidate is [design study 03](../../research/mockups/agentic-workspace-v3/README.md), with a new warm neutral/navy identity and source audit. Claude implementation remains stopped; read-only mockup review is separately authorized. Earlier application edits remain in the working tree and have not completed their final regression pass. The implementation instructions below are retained as history, not an instruction to resume them.

Date: 2026-10-09. The user rejected the current appearance as ugly. Implement a substantial visual pass on the actual application. Preserve the completed correctness corrections and reusable architecture. A passing test suite alone does not satisfy this assignment: inspect rendered screens and iterate.

## User-supplied interaction references (added during the task)

The user supplied two further references. They refine this assignment beyond styling:

- [Agentic Design: Chat Interface Patterns](https://agentic-design.ai/patterns/ui-ux-patterns/chat-interface-patterns) recommends preserved conversational context, richer content, visible activity and expandable citations, while warning that too many concurrent features increase cognitive load. Apply these selectively to supported e-agent tasks. Thread branching, reactions, collaborative editing and presence are outside the existing backend scope.
- [Alexandra Vasquez: Agentic UX — 7 principles for designing systems with agents](https://medium.com/design-bootcamp/agentic-ux-7-principles-for-designing-systems-with-agents-019512c2caa9) (2026-02-16) emphasizes coherent workflows, assistance in place, timely suggestions, shared context, familiar interactions, appropriately timed inputs and human control. Treat this as practitioner guidance, not measured proof that one visual style is superior.

### Application to this rework

These are e-agent-specific design decisions informed by the references:

1. **Keep the task in view.** The embedded overlay supports work on the host page. Users should not have to open the standalone workspace to understand a proposed change. The standalone overview remains a useful entry point, not a mandatory detour.
2. **A conversation has structure.** Distinguish the user's request, agent updates, exact proposed action, evidence and verified result with consistent components. Use one readable conversation column, with secondary context available alongside it in Workbench or through disclosures in compact mode.
3. **Context is visible and persistent.** Keep the task title and current status concise in the header. Keep available source/connection scope near the relevant action; do not re-request known inputs or add fake context chips. Preserve drafts and task selection through layout changes.
4. **Activity is factual.** Show human-readable summaries of recorded host events. No simulated progress percentages, invented working steps, confidence scores or hidden model reasoning. Source-linked explanations and recorded actions provide transparency.
5. **Controls stay close to the decision.** Keep inspect, reject and explicit approval together with the exact proposal. Use the existing cancel/reconcile paths only where supported. Do not add a generic Undo, pause/resume, proposal editing or background automation without the required host contract.
6. **Reveal detail as needed.** Keep sources, recorded activity and technical identifiers in useful disclosures. Every required material approval term still has to be inspectable before confirmation. Settings belong behind one familiar trigger.
7. **Ask only when needed.** Preserve the existing clarification flow in the same task. Do not invent an onboarding form, repeat known information or imply new memory persistence. Missing information remains explicit.

Acceptance scenarios now include: resume a task without losing context; understand whether it is working, waiting for input or waiting for review; inspect a source without losing the proposal; reject/cancel without accidental approval; and distinguish an unknown external effect from verified completion. Keep the calmer mockup proportions, but avoid adding decorative AI chrome that competes with these tasks.

## Reference and diagnosis

Open these images before editing:

- Target: `research/mockups/agentic-overlay/screenshots-v2/home.png` and `handoff-expanded.png`; consult the original HTML/CSS as the design reference.
- Current: `evidence/2026-10-09-overlay/workspace/desktop-overview.png`, `desktop-approval.png`, `overlay-approval.png`, and `desktop-connections.png`.

The current overview is more than 2,000px tall at desktop because it inherits the 44rem conversation width and stacks all eight technical capability cards in one column. The header shows five native select boxes. Technical IDs, internal implementation explanations and repeated status badges dominate. The reference has a wider composition, a quiet sidebar, a compact workflow grid, a prominent composer, clear typography and a restrained assistant header. Restore that visual direction without fabricating capabilities, users or connections.

## Concrete design direction

### Workspace and overview

1. Use a quiet approximately 224px desktop sidebar, a subtle cool-neutral canvas, white content surfaces and a restrained violet accent. Build a simple vector brand mark and consistent line icons through reusable components; do not add a large icon framework or remote assets just for this pass.
2. Give the overview its own wide layout (roughly 1080–1160px content width at a 1440px viewport with 40–48px side gutters). It is not a chat transcript. Keep conversation width constraints for actual task reading only.
3. Use a strong, left-aligned 40–44px desktop headline with tight but readable line height and a short supporting sentence. Aim for the reference's two-line dark/violet hierarchy. Reduce the current vacant top area and keep the composer in the first viewport. Mobile scales to roughly 30–32px with appropriate line wrapping.
4. Make the composer one deliberate, broad surface, around 110–130px tall in the desktop overview. Use a restrained border, clean placeholder, compact send affordance with an accessible name and quiet keyboard help. Keep existing draft, IME and submission semantics.
5. Render catalog items in a responsive **three-column desktop / two-column medium / one-column mobile** grid. Aim for compact 150–190px cards, with title, two or three lines of useful description, a quiet availability indicator and optional expandable details. Keep every installed task reachable; do not manufacture unavailable future workflows to match a screenshot.
6. Avoid raw contract IDs as permanent card content. Put technical identifiers in a labelled Details disclosure. The existing server title remains the source; improve server-side generic formatting or existing domain-owned presentation metadata if needed, but never put a dictionary of providers or business contracts in `ui/`. Keep any metadata change bounded and document/test it.
7. Remove implementation jargon from the primary flow: for example, replace the long “installed and admitted ... these are not buttons ...” paragraph with short user-oriented copy. Keep genuine limits, such as session-only history, concise and visible. Domain restrictions and exact action terms must not be removed from review.
8. Prefer a compact recent-work section beneath the grid, with a concise empty state. Avoid duplicate headings, multiple paragraphs saying the same thing, or a second huge empty card.

### Header, preferences and navigation

1. The default header must not look like an admin form. Keep brand/context, concise task status, a compact placement control where useful and one clearly labelled settings trigger. Put language/theme/appearance/density in a keyboard-accessible preferences popover or disclosure; pinned settings must retain current behavior.
2. Use consistent icons, spacing, active states and focus rings for navigation. Keep supported routes only; no fabricated Needs review inbox, tenant avatar, timestamps or user identity.
3. Preserve public slot IDs and behavioral test selectors. Update browser helpers to open preferences through their real UI when a test changes a setting; do not keep dropdowns visible solely to avoid adjusting tests. Never force-click hidden controls or weaken approval/focus tests.

### Assistant surfaces and review

1. Make the floating assistant look intentional: clean compact header, white body, subtle border/shadow and proportional radius. Keep settings out of its main header row. Eliminate the current stacked toolbar and oversized full-width status pill.
2. Workbench should use a clear primary review column and a quieter context/evidence column, similar to the reference. Docked/compact use the same components with a sensible single-column hierarchy.
3. Reduce repeated task headings and redundant prose. Distinguish user request, agent response, proposed action and supporting evidence through typography and spacing, not many nested bordered boxes.
4. Review still displays **every exact material field**, findings, approval expiry and the explicit confirmation flow. Improve field rows/typography and action alignment; do not replace authoritative terms with a pretty summary. Keep unknown effects explicit. Test sticky actions for overlap and ensure terms remain scrollable at 320px and in narrow containers.
5. Connections should use a considered grid/list hierarchy: readable identity and scope, quiet status, compact metadata disclosure. Unknown health must remain unknown. No decorative fake provider logos or connect buttons.

### Styling discipline

Retain semantic tokens, React Aria, plain scoped CSS and the current package boundaries. Use the same primitives across hosts. Do not turn the visual pass into a framework rewrite or pile late overrides into one global stylesheet. Co-locate changed feature styles and keep aggregate CSS working in the shadow root. All copy remains in EN/VI catalogs. Keep light, dark and high-contrast readable; respect reduced motion.

## Completion and evidence

1. First implement the overview/header and render desktop/mobile screenshots. Compare them with the reference before extending the treatment to review and Connections. Do not call the pass complete on code inspection alone.
2. Capture final desktop overview, session work, Connections, pending review, Workbench, compact overlay, dark review and mobile overview/review into a **new** `evidence/2026-10-09-visual-rework/` directory. Keep previous evidence untouched. Use the existing fixture screenshot workflow; use a neutral host for showcase captures while retaining the hostile-host CSS conformance test.
3. Run `pnpm --dir ui check` and full conformance, including `route-regressions.spec.ts` and `route-transitions.spec.ts`. Add focused settings keyboard/focus and layout checks as needed. Run relevant backend checks if display metadata changes. Do not access live business systems.
4. Inspect the final screenshots and fix overflow, awkward hierarchy, dense chrome, excessive page height or tiny text before reporting success. At desktop, the overview should visibly show a multi-column catalog beneath the composer; the default header should not expose a row of settings selects.
5. Write `docs/handoffs/2026-10-09-overlay-visual-rework-results.md` with what changed, before/after evidence paths, actual checks and limitations. No commits, pushes or deployment. Preserve all existing work and the five correctness fixes.
