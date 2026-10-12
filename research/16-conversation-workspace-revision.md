# Conversation-first enterprise workspace

Date: 2026-10-10. Status: candidate mockup responding to owner rejection of study 03.

The owner identified an information hierarchy failure: the dashboard and fixed navigation dominated an experience meant to center on conversation. A complete source audit and a passing code review did not establish that the design met this need.

[Study 04](mockups/agentic-chat-v4/README.md) places chat at the center, starts left navigation collapsed and opens the task artifact in a closable workspace on the right. Sources and activity belong inside that workspace. Mobile switches between conversation and artifact instead of showing compressed columns. Earlier mockups remain intact.

The design distinction is between conversation as the entry/coordination surface and structured views for reviewing concrete work. Enterprise breadth comes from supported capabilities and authorization, not a homepage catalog. This mockup still uses six explicitly fictional examples; it makes no new product-support claim.

Run and verification instructions are in the study README and QA report. This is a presentation candidate only. No production contracts, ADRs, live integrations or release qualification changed. Production implementation stays paused.

The follow-up [component system](mockups/agentic-chat-v4/design-system/README.md) adds shared warm-light/dark/high-contrast tokens, an original icon family, interactive component states and responsive rules. These sources now also drive the mockup. Browser verification covers phone, tablet, desktop and short landscape; physical-device and production adoption work remains separate.

A subsequent [default foundation review](mockups/agentic-chat-v4/design-system/FOUNDATION-REVIEW.md) replaced the thin mark with the connected graph identity and added an embedded Shadow DOM/container specimen. This closes the gap between standalone viewport screenshots and evidence for a docked overlay, without claiming production adoption.
