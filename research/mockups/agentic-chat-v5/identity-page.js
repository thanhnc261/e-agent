import { logo, logoFor, pose, poseCaption, v4Pose, standaloneSvg, wordmark } from "./identity.js";

const $ = s => document.querySelector(s);
const brand = () => getComputedStyle(document.documentElement).getPropertyValue("--ea-color-brand").trim();

function applyTheme(value) {
  if (value === "light") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = value;
  refreshDownload();
  if (typeof variantUrls !== "undefined") renderVariants();
}
function refreshDownload() {
  const blob = new Blob([standaloneSvg(brand() || "#4f8a74")], { type: "image/svg+xml" });
  const link = $("#identity-download");
  if (link.href.startsWith("blob:")) URL.revokeObjectURL(link.href);
  link.href = URL.createObjectURL(blob);
}

$("#identity-mark").innerHTML = logo();
$("#identity-lockup").innerHTML = `<span class="v5-lockup-mark">${logoFor(pose, "e-agent symbol")}</span><span class="v5-lockup-word">${wordmark()}</span>`;
$("#identity-pose-caption").textContent = poseCaption;
$("#pose-v4").innerHTML = logoFor(v4Pose, "v4 pose");
$("#pose-v5").innerHTML = logoFor(pose, "v5 pose");
document.querySelectorAll(".v5-theme-mark").forEach(e => (e.innerHTML = logo()));
// Lockup variants: brand colour read from each themed specimen's token, never hard-coded here.
const variantUrls = [];
function renderVariants() {
  variantUrls.forEach(u => URL.revokeObjectURL(u));
  variantUrls.length = 0;
  $("#identity-variants").innerHTML = ["light", "dark", "high-contrast", "mono"]
    .map(
      v =>
        `<figure class="v5-theme" ${v === "mono" ? "" : `data-theme="${v}"`} data-variant="${v}"><div class="v5-lockup v5-variant-lockup ${v === "mono" ? "v5-mono" : ""}"><span class="v5-lockup-mark">${logo()}</span><span class="v5-lockup-word">${wordmark()}</span></div><a download="e-agent-v5-${v}.svg">Download ${v} symbol</a></figure>`,
    )
    .join("");
  document.querySelectorAll("#identity-variants figure").forEach(fig => {
    const style = getComputedStyle(fig);
    const colour = (fig.dataset.variant === "mono"
      ? style.getPropertyValue("--ea-color-text")
      : style.getPropertyValue("--ea-color-brand")
    ).trim();
    const url = URL.createObjectURL(new Blob([standaloneSvg(colour)], { type: "image/svg+xml" }));
    variantUrls.push(url);
    fig.querySelector("a").href = url;
  });
}
renderVariants();
["tile-32", "tile-48", "launcher", "author"].forEach(id => ($("#" + id).innerHTML = logo()));
$("#author").insertAdjacentHTML("beforeend", "e-agent");
$("#identity-sizes").innerHTML = [24, 32, 40, 48, 64, 96]
  .map(size => `<figure><span style="width:${size}px;height:${size}px" class="v5-size">${logo()}</span><figcaption>${size}px</figcaption></figure>`)
  .join("");
$("#theme").addEventListener("change", e => applyTheme(e.target.value));
const requested = new URLSearchParams(location.search).get("theme");
const initial = ["dark", "high-contrast"].includes(requested) ? requested : "light";
$("#theme").value = initial;
applyTheme(initial);
