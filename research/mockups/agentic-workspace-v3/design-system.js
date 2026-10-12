import { iconPaths, icon, paintIcons } from "./icons.js";
const palette = [
  ["Canvas", "--canvas"],
  ["Surface", "--surface"],
  ["Text", "--text"],
  ["Action", "--action"],
  ["Assistant", "--ai"],
  ["Verified", "--green"],
];
function swatches() {
  const styles = getComputedStyle(document.body);
  document.querySelector("#swatches").innerHTML = palette
    .map(
      ([name, role]) =>
        `<div class="color-swatch"><i style="background:var(${role})"></i><strong>${name}</strong><span>${styles.getPropertyValue(role).trim()}</span></div>`,
    )
    .join("");
}
document.querySelector("#icon-grid").innerHTML = Object.keys(iconPaths)
  .map(
    (name) =>
      `<a class="icon-tile" href="assets/icons/${name}.svg" download aria-label="Download ${name} icon">${icon(name)}<span>${name}</span></a>`,
  )
  .join("");
document.querySelector("#kit-theme").addEventListener("click", () => {
  document.body.classList.toggle("dark");
  swatches();
});
document
  .querySelectorAll("[data-demo]")
  .forEach((button) =>
    button.addEventListener(
      "click",
      () =>
        (document.querySelector("#kit-announcement").textContent =
          button.dataset.demo + " · component demonstration only"),
    ),
  );
document.querySelector("#kit-composer").addEventListener("submit", (event) => {
  event.preventDefault();
  document.querySelector("#kit-announcement").textContent =
    "Intent captured locally for this component example. No task was executed.";
});
paintIcons();
swatches();
