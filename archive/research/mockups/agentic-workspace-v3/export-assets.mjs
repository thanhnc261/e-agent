import { iconPaths, logoGlyph } from "./icons.js";
import { mkdir, writeFile } from "node:fs/promises";
const directory = new URL("./assets/", import.meta.url);
await mkdir(new URL("./icons/", directory), { recursive: true });
const svg = (content, viewBox = "0 0 32 32") =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}">${content}</svg>\n`;
for (const [name, foreground, background] of [
  ["logo-mark", "#ffffff", "#233f70"],
  ["logo-mark-dark", "#172435", "#aecbf2"],
  ["logo-mark-mono", "#202321", "none"],
]) {
  await writeFile(
    new URL(name + ".svg", directory),
    svg(
      `<rect width="32" height="32" rx="8" fill="${background}"/><g color="${foreground}">${logoGlyph}</g>`,
    ),
  );
}
await writeFile(
  new URL("logo-wordmark.svg", directory),
  svg(
    `<rect width="32" height="32" rx="8" fill="#233f70"/><g color="#fff">${logoGlyph}</g><text x="43" y="24" fill="#202321" font-size="25" font-weight="600" letter-spacing="-1" font-family="system-ui,Segoe UI,sans-serif">e-agent</text>`,
    "0 0 148 32",
  ),
);
for (const [name, path] of Object.entries(iconPaths))
  await writeFile(
    new URL(`icons/${name}.svg`, directory),
    svg(
      `<path d="${path}" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/>`,
      "0 0 24 24",
    ),
  );
await writeFile(
  new URL("icons.svg", directory),
  `<svg xmlns="http://www.w3.org/2000/svg">${Object.entries(iconPaths)
    .map(
      ([name, path]) =>
        `<symbol id="${name}" viewBox="0 0 24 24"><path d="${path}" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"/></symbol>`,
    )
    .join("")}</svg>\n`,
);
console.log(
  `Exported four logo assets and ${Object.keys(iconPaths).length} icons plus a sprite.`,
);
