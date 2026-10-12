import { mkdir, writeFile, readFile } from "node:fs/promises";
import { iconPaths } from "./icons.js";
import { logoGlyph, logoGlyphFor, wordmarkGlyph } from "./brand.js";
const emit = async (url, content) => {
  if (process.argv.includes("--check")) {
    if ((await readFile(url, "utf8")) !== content) throw Error(`Asset drift: ${url.pathname}`);
  } else await writeFile(url, content);
};
const t = JSON.parse(await readFile(new URL("generated/tokens.json", import.meta.url), "utf8"));
const out = new URL("generated/assets/", import.meta.url);
await mkdir(new URL("icons/", out), { recursive: true });
for (const rotation of [15, 22.5, 30]) {
  await emit(
    new URL(`logo-angle-${rotation}.svg`, out),
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" color="${t.light["color.brand"]}">${logoGlyphFor({ rotation, tilt: 35 })}</svg>\n`,
  );
}
const directions = JSON.parse(await readFile(new URL("identity-directions.json", import.meta.url), "utf8"));
for (const concept of directions.concepts) {
  await emit(
    new URL(`concept-${concept.id}.svg`, out),
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">${concept.glyph}</svg>\n`,
  );
}
const path = d =>
  `<path d="${d}" fill="none" stroke="currentColor" stroke-width="${t.light["icon.stroke"]}" stroke-linecap="round" stroke-linejoin="round"/>`;
for (const [name, d] of Object.entries(iconPaths))
  await emit(
    new URL(`icons/${name}.svg`, out),
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">${path(d)}</svg>\n`,
  );
await emit(
  new URL("icons.svg", out),
  `<svg xmlns="http://www.w3.org/2000/svg">${Object.entries(iconPaths)
    .map(([name, d]) => `<symbol id="${name}" viewBox="0 0 24 24">${path(d)}</symbol>`)
    .join("")}</svg>\n`,
);
for (const [name, fg, bg] of [
  ["logo-light", t.light["color.accent-text"], t.light["color.brand"]],
  ["logo-dark", t.dark["color.accent-text"], t.dark["color.brand"]],
  ["logo-mono", t.light["color.text"], "none"],
])
  await emit(
    new URL(`${name}.svg`, out),
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="${bg}"/><g color="${fg}"><g transform="translate(4 4) scale(.75)">${logoGlyph}</g></g></svg>\n`,
  );
for (const theme of ["light", "dark", "high-contrast"]) {
  const colors = t[theme];
  const lockup = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 176 36"><g color="${colors["color.brand"]}">${logoGlyph}</g><g transform="translate(45 0)" color="${colors["color.text"]}">${wordmarkGlyph}</g></svg>\n`;
  await emit(new URL(`logo-lockup-${theme}.svg`, out), lockup);
  if (theme === "light") await emit(new URL("logo-wordmark.svg", out), lockup);
}
await emit(
  new URL("logo-symbol.svg", out),
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">${logoGlyph}</svg>\n`,
);
await emit(
  new URL("generated/icon-names.d.ts", import.meta.url),
  `// Generated from icons.js\nexport type IconName = ${Object.keys(iconPaths).map(JSON.stringify).join(" | ")};\n`,
);
console.log(
  `Exported ${Object.keys(iconPaths).length} icons, sprite and theme-aware connected graph identity assets.`,
);
