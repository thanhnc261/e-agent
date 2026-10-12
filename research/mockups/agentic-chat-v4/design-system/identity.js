import { logo, logoGlyphFor, wordmark, defaultLogoPose } from "./brand.js";
const theme = getComputedStyle(document.documentElement);
const response = await fetch(new URL("./tokens/palette-studies.json", import.meta.url));
if (!response.ok) throw new Error("Unable to load palette choices");
const studies = await response.json();
const colorControl = document.querySelector("#identity-colors");
let selectedStudy =
  studies.find(study => study.id === new URLSearchParams(location.search).get("palette")) || studies[0];
const roles = [...new Set(studies.flatMap(study => Object.keys(study.roles)))];
const defaultBrand = theme.getPropertyValue("--ea-color-brand").trim();
colorControl.innerHTML = studies
  .map(
    study =>
      `<button type="button" class="brand-color" data-palette="${study.id}" aria-pressed="false"><span style="background:${study.roles.brand || defaultBrand}" aria-hidden="true"></span>${study.name.replace(" · current", "")}</button>`,
  )
  .join("");
function applyPalette() {
  for (const role of roles) document.documentElement.style.removeProperty(`--ea-color-${role}`);
  for (const [role, value] of Object.entries(selectedStudy.roles))
    document.documentElement.style.setProperty(`--ea-color-${role}`, value);
  colorControl
    .querySelectorAll("button")
    .forEach(button =>
      button.setAttribute("aria-pressed", String(button.dataset.palette === selectedStudy.id)),
    );
  document.querySelector("#identity-color-status").textContent =
    `${selectedStudy.name.replace(" · current", "")} · applied to this preview and your SVG download`;
  const swatches = document.querySelector("#identity-palette");
  swatches.setAttribute("aria-label", `${selectedStudy.name} palette`);
  swatches.innerHTML = [
    ["brand", "Logo color"],
    ["canvas", "Canvas"],
    ["surface", "Surface"],
    ["text", "Ink"],
  ]
    .map(
      ([role, label]) =>
        `<div><span style="background:var(--ea-color-${role})" aria-hidden="true"></span><strong>${label}</strong><small>${theme.getPropertyValue(`--ea-color-${role}`).trim()}</small></div>`,
    )
    .join("");
}
let rotation = defaultLogoPose.rotation;
let downloadUrl;
const tiltControl = document.querySelector("#identity-tilt");
const depthControl = document.querySelector("#identity-depth");
const shadowControl = document.querySelector("#identity-shadow");
const finishControl = document.querySelector("#identity-finish");
const colorModeControl = document.querySelector("#identity-color-mode");
if (new URLSearchParams(location.search).get("nodes") === "multicolor") colorModeControl.value = "multicolor";
const angles = document.querySelector("#identity-angles");
angles.innerHTML = [15, 22.5, 30]
  .map(
    angle =>
      `<button type="button" class="brand-angle" data-rotation="${angle}" aria-label="Rotate ${angle} degrees clockwise" aria-pressed="${rotation === angle}"><span class="brand-angle-mark"></span><span>${angle}°</span></button>`,
  )
  .join("");
function render() {
  const tilt = Number(tiltControl.value);
  const depth = Number(depthControl.value);
  const shadow = shadowControl.value;
  const finish = finishControl.value;
  const colorMode = colorModeControl.value;
  const nodeColors = ["clay", "blue", "sage-lagoon", "lavender", "sea-glass", "soft-lagoon"]
    .filter(id => id !== selectedStudy.id)
    .slice(0, 4)
    .map(id => studies.find(study => study.id === id).roles.brand || defaultBrand);
  const pose = { rotation, tilt, depth, shadow, finish, colorMode, nodeColors };
  document.querySelector("#identity-mark").innerHTML = logo(pose);
  document.querySelector("#identity-lockup").innerHTML =
    `<div class="brand-lockup">${logo(pose)}${wordmark()}</div>`;
  document.querySelector("#identity-pose-caption").textContent =
    `${rotation}° clockwise · ${tilt}° backward tilt · ${depthControl.selectedOptions[0].text.toLowerCase()} depth · ${shadow} shadow · ${finish} surface`;
  angles.querySelectorAll("button").forEach(button => {
    const angle = Number(button.dataset.rotation);
    button.setAttribute("aria-pressed", String(angle === rotation));
    button.querySelector(".brand-angle-mark").innerHTML = logo({ ...pose, rotation: angle });
  });
  document.querySelector("#identity-variants").innerHTML = ["light", "dark", "high-contrast"]
    .map(
      theme =>
        `<article class="brand-variant" data-theme="${theme}">${logo()}<a href="design-system/generated/assets/logo-lockup-${theme}.svg" download>Download ${theme} default lockup</a></article>`,
    )
    .join("");
  document.querySelector("#identity-sizes").innerHTML = [24, 32, 40, 48, 64]
    .map(
      size =>
        `<span>${logo(pose).replace('class="ea-brand-symbol"', `class="ea-brand-symbol" style="width:${size}px;height:${size}px"`)}<small>${size}px</small></span>`,
    )
    .join("");
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" color="${theme.getPropertyValue("--ea-color-brand").trim()}">${logoGlyphFor(pose)}</svg>`;
  downloadUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  const download = document.querySelector("#identity-selected-download");
  download.href = downloadUrl;
  download.download = `e-agent-${selectedStudy.id}-${rotation}-${tilt}-depth-${depth}-${shadow}-shadow-${finish}-${colorMode}.svg`;
}
angles.addEventListener("click", event => {
  const button = event.target.closest("button[data-rotation]");
  if (!button) return;
  rotation = Number(button.dataset.rotation);
  render();
});
tiltControl.addEventListener("change", render);
depthControl.addEventListener("change", render);
shadowControl.addEventListener("change", render);
finishControl.addEventListener("change", render);
colorModeControl.addEventListener("change", render);
colorControl.addEventListener("click", event => {
  const button = event.target.closest("button[data-palette]");
  if (!button) return;
  selectedStudy = studies.find(study => study.id === button.dataset.palette);
  applyPalette();
  render();
});
window.addEventListener("pagehide", () => {
  if (downloadUrl) URL.revokeObjectURL(downloadUrl);
});
// Regenerate the download URL when returning from the browser's back/forward cache.
window.addEventListener("pageshow", event => {
  if (event.persisted) render();
});
applyPalette();
render();
