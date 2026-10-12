# Modern enterprise agent overlay: research-first UX brief

Date: 2026-10-08. Status: research and candidate direction, not an accepted visual design or implementation instruction.

The owner clarified that the requirement is a modern enterprise agent UI/UX overlay, with research preceding design and implementation. The previous Workbench/layout selector is existing implementation evidence, not proof that the requested visual experience has been achieved. This report preserves the earlier research and does not change application code or architecture decisions.

## Requirement interpretation

Create a polished agent experience that sits over the enterprise application and helps users delegate business tasks, understand what is happening, inspect proposed changes, intervene and recognize verified outcomes. The visual treatment, information hierarchy and interactions must work together. Retain the original requirement for switching the overlay from the UI; whether that switch selects a visual preset, presentation mode or both must be made explicit in the subsequent design.

Research should inform a reference board and candidate designs before additional implementation. A working layout, a passing browser test or a generic approval dashboard does not validate visual quality or usability.

## Primary references reviewed

Reviewed on 2026-10-08. These are published vendor design guidelines and product examples; they do not establish comparative usability or production guarantees for e-agent.

| Source | Research finding | Application hypothesis |
|---|---|---|
| [Microsoft Design: UX design for agents](https://microsoft.design/articles/ux-design-for-agents/) (2025-04-11) | Agents need discoverability, foreground/background continuity, visible state, user control, appropriate uncertainty and concise familiar interactions | A small persistent entry point opens a focused task surface; users can leave and return, see what needs attention and inspect supported activity |
| [Carbon for AI](https://www.carbondesignsystem.com/building-blocks/foundations/carbon-for-ai) (updated 2026-08-12) | AI has a distinct visual identity; explainability is contextual and progressive; subtle light effects identify AI rather than decorate unrelated controls | Give the assistant an identifiable header/composer and AI-origin treatment; use a brief evidence summary with drill-down, preserving readable business content |
| [SAP: Designing the Autonomous Enterprise](https://www.sap.com/design/stories-resources/designing-the-autonomous-enterprise) | Joule Work demonstrates intent-driven conversations and context-adaptive business spaces, with light/dark product examples | Render task-specific artifacts and business context rather than forcing every result into a transcript or permanent field grid |
| [Salesforce: Agentic Experience Design](https://www.salesforce.com/blog/ux-shift-to-agentic-experience-design/) (2025-08-11) | Intent, transparent coordination, available capabilities and graceful degradation shape the experience | State what can be done and what needs user action; explain unavailable capability and recovery paths in business language |

Microsoft's guidance is partly forward-looking. SAP's page identifies an early-adopter program; its workspace examples are design references, not evidence of generally available capability in e-agent. Salesforce's article includes author prototypes and opinion. None justifies introducing multi-agent architecture, generated executable UI or unsupported autonomy into this MVP.

## What the previous UI misses

This is a heuristic assessment of the captured fixture screens, not a user study.

- The approval field grid dominates the surface. Users must work through references before understanding the business purpose and decision.
- The task is repeated in multiple places while the context panel repeats generic “Read recorded” entries. These consume space without explaining the work.
- Evidence is primarily behind a collapsed control rather than summarized at the point where a user evaluates a proposal.
- The header combines layout, language, theme and cancellation controls without a clear primary interaction hierarchy.
- A wider panel and accent border change geometry and styling but do not establish a coherent modern agent experience.

Existing exact review, explicit approval and independent verification remain necessary. Better information hierarchy should make them understandable and reachable, not weaken them.

## Candidate UX model

The interaction should follow: **set intent → clarify context → follow work → review a proposed business artifact → explicitly approve → inspect the independently verified result**. This is a design model; not every step is required for every task.

| State | User needs | Candidate presentation |
|---|---|---|
| Ready | Know what the assistant can do | Short capability statement, a few admitted task examples, prominent composer; avoid a wall of empty panels |
| Working | Know that work is active and whether intervention is needed | Concise authoritative state, supported milestone summary, expandable activity; no simulated reasoning or invented progress |
| Clarification | Supply missing information | A focused inline question with relevant context; preserve the original task |
| Review | Understand purpose, impact and exact changes | Business summary above a structured proposal; complete normalized terms accessible before explicit confirmation |
| Executing/verifying | Distinguish approval, committed effect and verified success | Separate honest state labels; suppress claims of completion until independent verification supports them |
| Uncertain/failed | Know what happened and what to do next | A clear exception card with authorized recovery actions; never encourage blind retry of an uncertain write |
| Complete | Identify the actual result | Verified artifact/reference and evidence, with an appropriate next action |

Summaries and proposed artifacts must come from supported host/schema projections. If readable names, explanations or progress are unavailable, the design must show that limitation. Do not manufacture them in the frontend. Evidence explanations are source-grounded public summaries, not hidden chain-of-thought.

## Visual directions to explore

These are project hypotheses, not requirements imposed by the sources. They need a reference board and comparable mockups before selection.

1. **Calm enterprise assistant — recommended starting direction.** Warm neutral canvas, crisp white surfaces, charcoal text, restrained indigo accent, strong typography, consistent icons and modest rounded corners. A compact assistant identity and quiet elevation distinguish the overlay. Most visual emphasis goes to the task and business artifact.
2. **AI presence.** The same readable content structure with limited light/gradient treatment around the assistant identity and composer. Separate AI suggestions from host-verified facts through labels and consistent styling. Avoid glow across tables, approvals or unrelated content.
3. **Dense operator.** Tighter spacing, stronger state/exception signaling and immediately accessible supporting context for frequent users. This is appropriate only if user research confirms that simultaneous monitoring matters.

The recommended starting composition is a focused floating surface: concise header, task stream with structured artifacts, persistent composer where input is relevant, and contextual evidence/details revealed when needed. Expansion can provide more room for comparison/review. A permanent second inspector column should be justified by the task rather than imposed on every state.

Visual switching should be separate from changes to business state. The next design should show how users preview/select presets, distinguish appearance from floating/docked/expanded presentation, and retain work through a change. Naming and placement remain design questions rather than automatically reusing the current “View” menu.

## Research-to-design deliverables

Before further application changes:

1. A visual reference board with annotated examples of header, composer, proposal artifact, activity, evidence, exception and verified result patterns.
2. Two or three comparable high-fidelity candidate overlays for the same bounded procurement scenario; include ready, working, review, uncertain outcome and verified result, with mobile and expanded treatment.
3. A chosen typography/color/spacing/elevation/icon system, component anatomy and interaction specification; define the overlay switch explicitly.
4. Usability evaluation around delegation clarity, proposal comprehension, discoverability of evidence, intervention and recovery. Automated browser checks subsequently verify mechanics; they cannot substitute for user evaluation or establish design quality.

This turn performs research and records candidate directions only. It introduces no application changes, assets, new UI libraries or backend capabilities.
