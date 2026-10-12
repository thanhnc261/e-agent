/** Connected nodes projected onto a tilted plane. Shared by inline and exported SVGs. */
export const defaultLogoPose = Object.freeze({
  rotation: 22.5,
  tilt: 35,
  depth: 3,
  shadow: "soft",
  finish: "glossy",
  colorMode: "brand",
});
const nodes = [
  [6.5, 6.5, 3],
  [25.5, 6.5, 3],
  [16, 16, 3.5],
  [6.5, 25.5, 3],
  [25.5, 25.5, 3],
];
const radians = degrees => (degrees * Math.PI) / 180;
const number = value => Number(value.toFixed(3));
export function logoGlyphFor({
  rotation = defaultLogoPose.rotation,
  tilt = defaultLogoPose.tilt,
  depth = defaultLogoPose.depth,
  shadow = defaultLogoPose.shadow,
  finish = defaultLogoPose.finish,
  colorMode = defaultLogoPose.colorMode,
  nodeColors = [],
} = {}) {
  if (
    !Number.isFinite(rotation) ||
    rotation < 0 ||
    rotation > 45 ||
    !Number.isFinite(tilt) ||
    tilt < 0 ||
    tilt > 55 ||
    !Number.isFinite(depth) ||
    depth < 0 ||
    depth > 5 ||
    !["none", "soft", "raised"].includes(shadow) ||
    !["satin", "glossy"].includes(finish) ||
    !["brand", "multicolor"].includes(colorMode) ||
    (colorMode === "multicolor" &&
      (!Array.isArray(nodeColors) ||
        nodeColors.length !== 4 ||
        nodeColors.some(color => typeof color !== "string" || !/^#[0-9a-f]{6}$/i.test(color))))
  )
    throw new RangeError("Logo pose outside the supported preview range");
  const turn = radians(rotation),
    lean = radians(tilt);
  const project = (x, y) => {
    const dx = x - 16,
      dy = y - 16;
    const rx = dx * Math.cos(turn) - dy * Math.sin(turn);
    const ry = dx * Math.sin(turn) + dy * Math.cos(turn);
    // Positive screen rotation is clockwise; upper nodes recede from the camera.
    const scale = 80 / (80 - ry * Math.sin(lean));
    return [16 + rx * scale, 16 + ry * Math.cos(lean) * scale];
  };
  const rings = nodes.map(([x, y, radius]) =>
    Array.from({ length: 64 }, (_, i) => {
      const angle = (i * Math.PI) / 32;
      return project(x + radius * Math.cos(angle), y + radius * Math.sin(angle));
    }),
  );
  const points = rings.flat();
  const minX = Math.min(...points.map(p => p[0])),
    maxX = Math.max(...points.map(p => p[0]));
  const minY = Math.min(...points.map(p => p[1])),
    maxY = Math.max(...points.map(p => p[1])) + depth;
  const fit = Math.min(28 / (maxX - minX), 28 / (maxY - minY));
  const place = ([x, y], depth = 0) => [
    number(16 + (x - (minX + maxX) / 2) * fit),
    number(16 + (y + depth - (minY + maxY) / 2) * fit),
  ];
  const layer = (offset, color = "currentColor", spread = 0) => {
    const centers = nodes.map(([x, y]) => place(project(x, y), offset));
    const edges = [0, 1, 3, 4].map(i => `M${centers[i].join(" ")}L${centers[2].join(" ")}`).join("");
    const discs = rings
      .map((ring, index) => {
        const xs = ring.map(p => p[0]),
          ys = ring.map(p => p[1]);
        const left = Math.min(...xs),
          right = Math.max(...xs),
          top = Math.min(...ys),
          bottom = Math.max(...ys);
        const [cx, cy] = place([(left + right) / 2, (top + bottom) / 2], offset);
        const paint =
          colorMode === "multicolor" && color === "currentColor" && index !== 2
            ? nodeColors[index < 2 ? index : index - 1]
            : color;
        return `<ellipse data-node="${index}" fill="${paint}" cx="${cx}" cy="${cy}" rx="${number(((right - left) * fit) / 2)}" ry="${number(((bottom - top) * fit) / 2)}"/>`;
      })
      .join("");
    return `<path d="${edges}" fill="none" stroke="${color}" stroke-width="${number(2.1 * fit + spread * 2)}" stroke-linecap="round"/><g fill="${color}" stroke="${color}" stroke-width="${number(spread * 2)}">${discs}</g>`;
  };
  // Solid extruded sidewalls, shaded from the chosen brand hue. No SVG IDs are
  // needed, so multiple instances and standalone downloads render identically.
  const sidewalls = [];
  for (let offset = depth; offset > 0; offset -= 0.3) {
    sidewalls.push(
      layer(offset),
      `<g opacity="${number(0.18 + (0.16 * offset) / Math.max(depth, 1))}">${layer(offset, "black")}</g>`,
    );
  }
  const highlights = rings
    .map(ring => {
      const top = ring.slice(33, 60).map(p => place(p));
      return `<path d="M${top.map(p => p.join(" ")).join("L")}"/>`;
    })
    .join("");
  // Layered specular patches model a broad studio light on each polished node.
  // Kept inside the top faces; this is a surface reflection, independent of cast shadow.
  const reflection =
    finish === "glossy"
      ? rings
          .map(ring => {
            const xs = ring.map(p => p[0]),
              ys = ring.map(p => p[1]);
            const left = Math.min(...xs),
              right = Math.max(...xs),
              top = Math.min(...ys),
              bottom = Math.max(...ys);
            const [cx, cy] = place([(left + right) / 2, (top + bottom) / 2]);
            const rx = ((right - left) * fit) / 2,
              ry = ((bottom - top) * fit) / 2;
            const glow = [1, 0.86, 0.72, 0.58]
              .map(
                scale =>
                  `<ellipse cx="${number(cx - rx * 0.12)}" cy="${number(cy - ry * 0.3)}" rx="${number(rx * 0.78 * scale)}" ry="${number(ry * 0.47 * scale)}" fill="white" opacity=".09"/>`,
              )
              .join("");
            return `${glow}<ellipse cx="${number(cx - rx * 0.17)}" cy="${number(cy - ry * 0.5)}" rx="${number(rx * 0.43)}" ry="${number(ry * 0.11)}" fill="white" opacity=".6"/>`;
          })
          .join("")
      : "";
  // Nested translucent silhouettes approximate a soft shadow entirely in vectors.
  // No filter IDs, external styles or raster effects: standalone exports match inline marks.
  const shadowLayers =
    shadow === "none"
      ? ""
      : [1, 0.75, 0.5, 0.25, 0]
          .map((falloff, i) => {
            const spread = falloff * (shadow === "raised" ? 0.9 : 0.65);
            const opacity = [0.018, 0.025, 0.035, 0.045, 0.055][i] * (shadow === "raised" ? 1.35 : 1);
            return `<g opacity="${number(opacity)}">${layer(depth, "black", spread)}</g>`;
          })
          .join("");
  const castShadow = shadowLayers
    ? `<g data-shadow="${shadow}" transform="translate(.45 ${shadow === "raised" ? 1 : 0.65})">${shadowLayers}</g>`
    : "";
  return `${castShadow}<g data-material="extruded">${sidewalls.join("")}<g data-face="${colorMode}">${layer(0)}</g><g data-finish="${finish}">${reflection}</g><g fill="none" stroke="white" stroke-opacity=".48" stroke-width="${number(0.4 * fit)}" stroke-linecap="round">${highlights}</g></g>`;
}
export const logoGlyph = logoGlyphFor();
// Custom geometric monoline lowercase lettering; independent of the graph symbol.
export const wordmarkGlyph =
  '<g fill="none" stroke="currentColor" stroke-width="3.1" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17h12v-1a6 6 0 1 0-2 5M24 16h5M48 22V11m0 5a6 6 0 1 0-12 0 6 6 0 0 0 12 0M66 11v14c0 6-9 7-11 2m11-11a6 6 0 1 0-12 0 6 6 0 0 0 12 0M73 17h12v-1a6 6 0 1 0-2 5M93 22V11m0 5c0-8 12-8 12 0v6M115 5v13c0 4 3 5 6 3m-10-10h10"/></g>';
export const logo = pose =>
  `<svg class="ea-brand-symbol" viewBox="0 0 32 32" aria-hidden="true" focusable="false">${pose ? logoGlyphFor(pose) : logoGlyph}</svg>`;
export const wordmark = () =>
  `<svg class="ea-brand-wordmark" viewBox="0 0 126 34" aria-hidden="true" focusable="false">${wordmarkGlyph}</svg>`;
