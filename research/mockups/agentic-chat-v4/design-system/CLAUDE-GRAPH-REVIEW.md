# Identity mark review — `agentic-chat-v4`

The revision does solve the stated problems: it's not a letter *e*, it's mirror-symmetric about x=16, and the three spokes sit at exact 120° intervals.

**1. Reads as an isometric cube, not a graph — HIGH**
*Screenshot:* at hero, header tile, all three variant cards and every size step, the mark reads as a 3D box. *Mechanism (from `brand.js:3`):* the hexagon outline passes through all six vertices, but nodes occupy only three alternating ones — so the three bare corners read as box edges and the center "Y" as the near corner of a cube. The brief asks for graph/ontology; the dominant read is container/package.

**2. Collapses at 16px — MEDIUM**
*Screenshot:* the 16px step in the size ramp is a dark clump; nodes and spokes are no longer separable. 20px is marginal; detail resolves from 24px. *Numbers:* at 16px the 32-unit viewBox scales 0.5× → 3px node discs, 1.2px strokes, and only ~3px of clear spoke between node edges. (As rendered in this screenshot; I can't see the device pixel ratio.) This contradicts `identity.html:38` — "Use the bare symbol at 16px and above."

**3. No accessible form of the symbol exists in the API — MEDIUM**
`brand.js:7-8`: `logo()` hardcodes `aria-hidden="true" focusable="false"` with no parameter and no `role="img"`/`<title>` variant. Correct for decorative use, and the header link plus the three "Download …" links do carry text names (screenshot). But `identity.html:38-40` prescribes a bare 48px overlay launcher — exactly the standalone-control case. The guidance at line 50 is prose, not enforcement. *Inference:* I did not read `identity.js` or `overlay.html`, so I can't confirm how the launcher is actually labelled.

**4. Glyph sits ~0.9 units high in the viewBox — LOW**
Content spans y≈1→29.2 (the round linejoin at the bottom vertex adds 1.2) against balanced 2.6/2.6 horizontal margins. Verifiable from `brand.js:3`; sub-pixel at these sizes. I am *not* claiming visible misalignment in the hero lockup.
