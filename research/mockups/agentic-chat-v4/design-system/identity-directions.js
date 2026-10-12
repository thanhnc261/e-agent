import { composerMarkup } from "./components.js";
import { icon } from "./icons.js";
const response = await fetch(new URL("./identity-directions.json", import.meta.url));
if (!response.ok) throw new Error("Unable to load identity directions");
const { concepts, palettes } = await response.json();
const symbol = concept =>
  `<svg class="direction-symbol" viewBox="0 0 64 64" aria-hidden="true" focusable="false">${concept.glyph}</svg>`;
document.querySelector("#direction-shapes").innerHTML = concepts
  .map(
    (c, i) =>
      `<label class="direction-option"><input type="radio" name="shape" value="${c.id}" ${i === 0 ? "checked" : ""} aria-label="${c.name} shape">${symbol(c)}<strong>${c.name}</strong><p>${c.description}</p><div class="direction-sizes">${symbol(c)}${symbol(c)}<span>24 / 32px</span></div></label>`,
  )
  .join("");
document.querySelector("#direction-colors").innerHTML = palettes
  .map(
    (p, i) =>
      `<label class="direction-color"><input type="radio" name="palette" value="${p.id}" ${i === 0 ? "checked" : ""}><i aria-hidden="true" style="--direction-swatch:${p.accent}"></i>${p.name}</label>`,
  )
  .join("");
const preview = document.querySelector("#direction-preview");
preview.dataset.theme = "light";
document.querySelector("#direction-composer").innerHTML = composerMarkup("direction-");
preview.querySelectorAll("[data-icon]").forEach(node => {
  node.innerHTML = icon(node.dataset.icon);
});
preview.querySelector("textarea").value = "Include the open decisions";
preview.querySelector(".send-button").disabled = false;
const feedback = preview.querySelector(".composer-note");
feedback.setAttribute("role", "status");
preview.querySelector("form").addEventListener("submit", event => {
  event.preventDefault();
  feedback.textContent = "Design preview · no message sent";
});
preview.querySelector("[data-action='add-context']").addEventListener("click", () => {
  feedback.textContent = "Design preview · sample context only";
});
function update() {
  const concept = concepts.find(c => c.id === document.querySelector('[name="shape"]:checked').value);
  const palette = palettes.find(p => p.id === document.querySelector('[name="palette"]:checked').value);
  const roles = {
    canvas: palette.canvas,
    surface: palette.surface,
    "surface-raised": palette.surface,
    text: palette.text,
    "text-muted": palette.muted,
    "text-subtle": palette.muted,
    border: palette.border,
    "border-subtle": palette.border,
    "border-strong": palette.muted,
    accent: palette.accent,
    "accent-strong": palette.hover,
    "accent-text": palette.surface,
    "accent-soft": palette.soft,
    "surface-hover": palette.soft,
    "message-user": palette.soft,
    focus: palette.accent,
  };
  Object.entries(roles).forEach(([role, color]) => preview.style.setProperty(`--ea-color-${role}`, color));
  preview.style.setProperty("--ea-component-field-border", "var(--ea-color-border-strong)");
  document.querySelector("#direction-lockup").innerHTML = `${symbol(concept)}<span>e-agent</span>`;
  document.querySelector("#direction-app-brand").innerHTML = `${symbol(concept)}<span>e-agent</span>`;
  document.querySelector("#direction-caption").textContent = `${concept.name} / ${palette.name}`;
  document.querySelector("#direction-download").href =
    `design-system/generated/assets/concept-${concept.id}.svg`;
  document.querySelector("#direction-status").textContent =
    `${concept.name} / ${palette.name} is an archived study. The current direction uses connected nodes and Warm Lagoon.`;
}
document
  .querySelectorAll('[name="shape"], [name="palette"]')
  .forEach(input => input.addEventListener("change", update));
update();
