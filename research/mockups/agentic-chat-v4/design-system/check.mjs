import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { build, resolve, cssValue } from "./build.mjs";
import { icon, iconPaths } from "./icons.js";
import { logoGlyph, logoGlyphFor, wordmarkGlyph, logo } from "./brand.js";
const values = await build(true);
assert.ok(logo().includes(logoGlyph));
assert.throws(() => logoGlyphFor({ rotation: NaN }), RangeError);
assert.throws(() => logoGlyphFor({ tilt: 90 }), RangeError);
assert.throws(() => logoGlyphFor({ depth: -1 }), RangeError);
assert.throws(() => logoGlyphFor({ depth: Infinity }), RangeError);
assert.throws(() => logoGlyphFor({ shadow: "unknown" }), RangeError);
assert.throws(() => logoGlyphFor({ finish: "unknown" }), RangeError);
assert.throws(() => logoGlyphFor({ colorMode: "multicolor" }), RangeError);
assert.throws(
  () => logoGlyphFor({ colorMode: "multicolor", nodeColors: ["bad", "#000000", "#000000", "#000000"] }),
  RangeError,
);
assert.doesNotMatch(logoGlyphFor({ shadow: "none" }), /data-shadow/);
assert.match(logoGlyphFor({ shadow: "raised" }), /data-shadow="raised"/);
for (const rotation of [15, 22.5, 30]) {
  const svg = await readFile(new URL(`generated/assets/logo-angle-${rotation}.svg`, import.meta.url), "utf8");
  assert.ok(svg.includes(logoGlyphFor({ rotation, tilt: 35 })), "Angle export drift");
}
for (const theme of ["light", "dark", "high-contrast"]) {
  const svg = await readFile(new URL(`generated/assets/logo-lockup-${theme}.svg`, import.meta.url), "utf8");
  assert.ok(svg.includes(logoGlyph) && svg.includes(wordmarkGlyph), "Identity export drift");
  assert.doesNotMatch(svg, /<(text|image)\b|font-family/, "Identity must remain vector-only");
}
assert.throws(() => resolve({ a: { $type: "color", $value: "{b}" } }, "a"), /Missing token/);
assert.throws(
  () => resolve({ a: { $type: "color", $value: "{b}" }, b: { $type: "color", $value: "{a}" } }, "a"),
  /cycle/,
);
assert.throws(() => cssValue({ $type: "mystery", $value: 1 }), /Unsupported/);
assert.throws(
  () => resolve({ a: { $type: "color", $value: "{b}" }, b: { $type: "number", $value: 1 } }, "a"),
  /type mismatch/,
);
assert.throws(() => cssValue({ $type: "dimension", $value: { value: 12, unit: "ms" } }), /Invalid/);
assert.throws(() => cssValue({ $type: "duration", $value: { value: 12, unit: "px" } }), /Invalid/);
assert.equal(cssValue({ $type: "color", $value: { colorSpace: "srgb", components: [1, 0, 0] } }), "#ff0000");
for (const value of [
  { colorSpace: "srgb", components: [NaN, 0, 0], alpha: 1 },
  { colorSpace: "srgb", components: [1, 0, 0], alpha: 2 },
  { colorSpace: "srgb", components: [1, 0, 0], alpha: NaN },
])
  assert.throws(() => cssValue({ $type: "color", $value: value }), /normalized sRGB/);
assert.throws(() => icon("nonexistent"), /Unknown icon/);
const luminance = hex =>
  [1, 3, 5]
    .map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    .reduce((s, c, i) => s + c * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => {
  const [lo, hi] = [luminance(a), luminance(b)].sort((x, y) => x - y);
  return (hi + 0.05) / (lo + 0.05);
};
const paletteStudies = JSON.parse(
  await readFile(new URL("tokens/palette-studies.json", import.meta.url), "utf8"),
);
const studyValues = Object.fromEntries(
  paletteStudies.map(study => [
    `study-${study.id}`,
    {
      ...values.light,
      ...Object.fromEntries(
        Object.entries(study.roles).map(([role, value]) => {
          assert.ok(`color.${role}` in values.light, `Unknown palette study role: ${role}`);
          assert.match(value, /^#[0-9a-f]{6}$/i);
          return [`color.${role}`, value];
        }),
      ),
    },
  ]),
);
for (const [theme, t] of Object.entries({ ...values, ...studyValues })) {
  for (const fg of ["text", "text-muted", "text-subtle"])
    for (const bg of ["canvas", "surface", "surface-sunken", "surface-selected", "message-user"])
      assert.ok(contrast(t["color." + fg], t["color." + bg]) >= 4.5, `${theme}: ${fg} on ${bg}`);
  for (const role of ["verified", "failed", "unknown", "progress"]) {
    assert.ok(
      contrast(t["color.status-" + role], t["color.status-" + role + "-surface"]) >= 4.5,
      `${theme}: ${role}`,
    );
    assert.ok(
      contrast(t["color.text-muted"], t[`color.status-${role}-surface`]) >= 4.5,
      `${theme}: muted text on ${role}`,
    );
  }
  assert.ok(
    contrast(t["color.action-danger-text"], t["color.action-danger"]) >= 4.5,
    `${theme}: destructive action`,
  );
  for (const bg of ["accent", "accent-strong"])
    assert.ok(contrast(t["color.accent-text"], t["color." + bg]) >= 4.5, `${theme}: action text`);
  for (const role of ["border-strong", "focus"])
    assert.ok(contrast(t["color." + role], t["color.surface"]) >= 3, `${theme}: ${role}`);
  for (const bg of ["canvas", "surface"])
    assert.ok(contrast(t["color.brand"], t[`color.${bg}`]) >= 3, `${theme}: brand visibility`);
  assert.ok(parseInt(t["control.height"]) >= 44);
  assert.ok(parseInt(t["control.min-target"]) >= 24);
}
const identityDirections = JSON.parse(
  await readFile(new URL("identity-directions.json", import.meta.url), "utf8"),
);
for (const p of identityDirections.palettes) {
  for (const fg of [p.text, p.muted]) {
    for (const bg of [p.canvas, p.surface, p.soft])
      assert.ok(contrast(fg, bg) >= 4.5, `${p.id}: identity text contrast`);
  }
  for (const bg of [p.accent, p.hover])
    assert.ok(contrast(p.surface, bg) >= 4.5, `${p.id}: identity action contrast`);
  assert.ok(contrast(p.accent, p.surface) >= 3, `${p.id}: identity focus contrast`);
}
for (const path of [
  "../styles.css",
  "components.css",
  "catalog.css",
  "brand.css",
  "overlay.css",
  "palettes.css",
  "identity-directions.css",
]) {
  const css = await readFile(new URL(path, import.meta.url), "utf8");
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,8}\b/, `Hard-coded color in ${path}`);
  for (const match of css.matchAll(/var\(--ea-([a-z0-9-]+)/g)) {
    assert.ok(
      Object.keys(values.light).some(k => k.replaceAll(".", "-") === match[1]),
      `Unresolved CSS token ${match[1]} in ${path}`,
    );
  }
}
const composition = await readFile(new URL("../styles.css", import.meta.url), "utf8");
const components = await readFile(new URL("components.css", import.meta.url), "utf8");
for (const name of Object.keys(values.light).filter(n => n.startsWith("component."))) {
  assert.ok(
    (composition + components).includes(`var(--ea-${name.replaceAll(".", "-")})`),
    `Unused component token: ${name}`,
  );
}
for (const name of [
  "control.min-target",
  "control.focus-offset",
  "motion.fast",
  "motion.base",
  "layer.base",
]) {
  assert.ok(
    (composition + components).includes(`var(--ea-${name.replaceAll(".", "-")})`),
    `Unused control token: ${name}`,
  );
}
for (const name of ["mobile", "compact"]) {
  assert.ok(
    composition.includes(`(max-width: ${values.light[`layout.${name}-breakpoint`]})`),
    `CSS breakpoint drift: ${name}`,
  );
}
const catalogCSS = await readFile(new URL("catalog.css", import.meta.url), "utf8");
const overlayCSS = await readFile(new URL("overlay.css", import.meta.url), "utf8");
assert.ok(
  overlayCSS.includes(`(width > ${values.light["layout.mobile-breakpoint"]})`),
  "Overlay container breakpoint drift",
);
assert.ok(
  overlayCSS.includes(`(max-width: ${values.light["layout.compact-breakpoint"]})`),
  "Overlay compact breakpoint drift",
);
assert.ok(catalogCSS.includes(`(max-width: ${values.light["layout.mobile-breakpoint"]})`));
const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
assert.doesNotMatch(app, /innerWidth\s*[<>]=?\s*\d+/, "Use generated media query in app logic");
for (const name of Object.keys(iconPaths)) {
  const svg = await readFile(new URL(`generated/assets/icons/${name}.svg`, import.meta.url), "utf8");
  assert.ok(svg.includes(iconPaths[name]), `Icon drift: ${name}`);
  assert.match(svg, /viewBox="0 0 24 24"/);
  assert.match(svg, /stroke="currentColor"/);
  assert.ok(svg.includes(`stroke-width="${values.light["icon.stroke"]}"`));
  assert.ok(icon(name).includes(`stroke-width="${values.light["icon.stroke"]}"`));
}
console.log(
  `PASS: ${Object.keys(values.light).length} tokens × 3 themes, aliases/output drift, text/status/action contrast, focus/control boundaries, ${Object.keys(iconPaths).length} icon assets, no component color literals.`,
);
