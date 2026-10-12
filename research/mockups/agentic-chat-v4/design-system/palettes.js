import { logo, wordmark } from "./brand.js";
import { composerMarkup } from "./components.js";
import { icon } from "./icons.js";
const headerBrand = document.querySelector(".ds-brand");
headerBrand.insertAdjacentHTML("afterbegin", `<span class="brand-mark">${logo()}</span>`);
const response = await fetch(new URL("./tokens/palette-studies.json", import.meta.url));
if (!response.ok) throw new Error("Unable to load palette studies");
const studies = await response.json();
for (const study of studies) {
  const card = document.createElement("article");
  card.className = "palette-card";
  card.dataset.theme = "light";
  for (const [role, value] of Object.entries(study.roles))
    card.style.setProperty(`--ea-color-${role}`, value);
  // The field alias is resolved on this preview scope, where the palette is overridden.
  card.style.setProperty("--ea-component-field-border", "var(--ea-color-border-strong)");
  card.innerHTML = `<header><div class="palette-lockup">${logo()}${wordmark()}</div><h2>${study.name}</h2><a href="identity.html?palette=${study.id}">Choose this color →</a><p class="palette-description">${study.description}</p></header><div class="palette-chat"><p class="palette-question">Prepare a handoff for the customer launch.</p><p class="palette-answer">I can pull together the latest notes, open decisions and owners.</p><p>I’ll prepare a draft for you to review before sharing it.</p>${composerMarkup(`${study.id}-`)}</div>`;
  for (const node of card.querySelectorAll("[data-icon]")) node.innerHTML = icon(node.dataset.icon);
  const textarea = card.querySelector("textarea");
  textarea.value = "Include open decisions and next steps";
  const send = card.querySelector(".send-button");
  send.disabled = false;
  const note = card.querySelector(".composer-note");
  note.setAttribute("role", "status");
  card.querySelector("form").addEventListener("submit", event => {
    event.preventDefault();
    note.textContent = "Palette preview only · message not sent";
  });
  card.querySelector("[data-action='add-context']").addEventListener("click", () => {
    note.textContent = "Palette preview only · context is illustrative";
  });
  document.querySelector("#palette-grid").append(card);
  const theme = getComputedStyle(card);
  const swatches = document.createElement("div");
  swatches.className = "palette-swatches";
  swatches.innerHTML = ["brand", "canvas"]
    .map(
      role =>
        `<span><i style="background:var(--ea-color-${role})" aria-hidden="true"></i><small>${role === "brand" ? "Brand" : "Canvas"} · ${theme.getPropertyValue(`--ea-color-${role}`).trim()}</small></span>`,
    )
    .join("");
  card.querySelector("header").append(swatches);
}
