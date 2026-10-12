import { logo } from "./brand.js";
import { icon } from "./icons.js";
import { composerMarkup, statusMarkup } from "./components.js";
import { MOBILE_QUERY } from "./generated/metrics.js";
const css = await fetch(new URL("./generated/overlay.css", import.meta.url)).then(r => {
  if (!r.ok) throw Error("Build the overlay CSS first");
  return r.text();
});
class FoundationPreview extends HTMLElement {
  connectedCallback() {
    if (this.shadowRoot) return;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${css}</style><section id="overlay-panel" class="overlay-frame" data-view="chat" aria-label="e-agent"><div class="overlay-interior"><header class="overlay-header"><span class="brand-mark">${logo()}</span><div class="overlay-heading"><strong>e-agent</strong><small>Delivery handoff · sample</small></div><button class="icon-button" id="close" aria-label="Close e-agent">${icon("close")}</button></header><div class="overlay-content"><section class="overlay-chat" aria-label="Conversation"><div class="overlay-messages"><h2>A clear handoff, ready to review.</h2><p>I brought the scope, owner and kickoff into one draft. Review the document before creating it.</p><button class="artifact-link" id="open-work">${icon("file")}<span><strong>Meridian · Delivery handoff</strong><small>Needs review · no action sent</small></span>${icon("arrow")}</button><p class="overlay-status">3 sample sources · signed scope, launch notes and delivery checklist</p><p>Creating the document and sharing it are separate decisions.</p><div id="local-messages" role="status"></div></div>${composerMarkup("overlay-")}</section><section class="overlay-work" aria-label="Proposed document"><h2>Meridian · Delivery handoff</h2>${statusMarkup("attention")}<div class="overlay-review"><dl class="terms"><div><dt>Project owner</dt><dd>Alex Morgan</dd></div><div><dt>Kickoff</dt><dd>19 October 2026</dd></div><div><dt>Destination</dt><dd>Documents / Delivery / Meridian</dd></div><div><dt>Audience</dt><dd>Delivery team · 8 members</dd></div></dl></div><p>Launch the customer portal for the APAC team. The agreed scope includes onboarding, reporting and a guided pilot.</p><p class="overlay-status">Revision 1 · fictional example</p><p id="review-result" role="status"></p></section></div><footer class="overlay-footer"><button class="secondary overlay-view-toggle" id="view-toggle">Open draft</button><button class="primary" id="review">Preview review</button></footer></div><dialog class="overlay-dialog" id="review-dialog" aria-labelledby="review-title"><h2 id="review-title">Review the sample document</h2><p>Create a document in Documents / Delivery / Meridian, visible to the delivery team (8 members), as Jamie Lee in the Northstar sample workspace. Proposal revision 1. No message will be sent.</p><p>This is a styling demonstration. It cannot execute or authorize an action.</p><div class="dialog-actions"><button class="secondary" id="back">Back</button><button class="primary" id="confirm">Confirm example</button></div></dialog></section><button class="overlay-launcher" id="overlay-launcher" aria-label="Open e-agent" aria-controls="overlay-panel" aria-expanded="true" hidden>${logo()}</button>`;
    const $ = s => root.querySelector(s),
      frame = $(".overlay-frame"),
      prompt = $("#overlay-prompt"),
      form = $("#overlay-composer");
    root.querySelectorAll("[data-icon]").forEach(e => (e.innerHTML = icon(e.dataset.icon)));
    const setView = view => {
      frame.dataset.view = view;
      $("#view-toggle").textContent = view === "chat" ? "Open draft" : "Back to chat";
    };
    $("#open-work").onclick = () => {
      setView("work");
      const heading = $(".overlay-work h2");
      heading.tabIndex = -1;
      heading.focus();
    };
    $("#view-toggle").onclick = () => setView(frame.dataset.view === "chat" ? "work" : "chat");
    const launcher = $("#overlay-launcher");
    $("#close").onclick = () => {
      frame.hidden = true;
      launcher.hidden = false;
      this.dataset.collapsed = "true";
      launcher.setAttribute("aria-expanded", "false");
      this.dispatchEvent(new CustomEvent("preview-placement", { bubbles: true }));
      launcher.focus();
    };
    launcher.onclick = () => {
      delete this.dataset.collapsed;
      frame.hidden = false;
      launcher.hidden = true;
      launcher.setAttribute("aria-expanded", "true");
      this.dispatchEvent(new CustomEvent("preview-placement", { bubbles: true }));
      $("#close").focus();
    };
    const resize = () => {
      prompt.style.height = "auto";
      prompt.style.height = Math.min(prompt.scrollHeight, 128) + "px";
      form.querySelector(".send-button").disabled = !prompt.value.trim();
    };
    prompt.addEventListener("input", resize);
    prompt.addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        form.requestSubmit();
      }
    });
    form.addEventListener("submit", e => {
      e.preventDefault();
      if (!prompt.value.trim()) return;
      $("#local-messages").textContent =
        `Saved locally: ${prompt.value}. No model or external action was invoked.`;
      prompt.value = "";
      resize();
    });
    $("[data-action=add-context]").onclick = () => {
      const target = $("#overlay-composer-context");
      target.hidden = false;
      target.innerHTML = `<span class="context-chip">${icon("file")}Signed scope<button type="button" aria-label="Remove source">${icon("close")}</button></span>`;
      target.querySelector("button").onclick = () => {
        target.hidden = true;
        target.textContent = "";
      };
    };
    $("#review").onclick = () => {
      $("#review-dialog").showModal();
      $("#back").focus();
    };
    const closeReview = () => {
      $("#review-dialog").close();
      $("#review").focus();
    };
    $("#review-dialog").addEventListener("cancel", event => {
      event.preventDefault();
      closeReview();
    });
    $("#back").onclick = closeReview;
    $("#confirm").onclick = () => {
      closeReview();
      const result = frame.dataset.view === "work" ? $("#review-result") : $("#local-messages");
      result.textContent = "Example confirmed locally. No business action was executed.";
      result.scrollIntoView({ block: "nearest" });
    };
    // Restore the explicit opener synchronously; Safari does not focus clicked buttons by default.
    root.addEventListener("keydown", event => {
      if ($("#review-dialog").open || frame.hidden) return;
      if (event.key === "Escape") {
        event.preventDefault();
        $("#close").click();
        return;
      }
      if (event.key !== "Tab" || frame.getAttribute("aria-modal") !== "true") return;
      const focusable = [
        ...frame.querySelectorAll('button:not(:disabled),textarea,input,select,a[href],[tabindex="0"]'),
      ].filter(e => e.getClientRects().length);
      const first = focusable[0],
        last = focusable.at(-1);
      if (event.shiftKey && root.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && root.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    resize();
  }
}
customElements.define("e-agent-foundation-preview", FoundationPreview);
const preview = document.querySelector("#overlay-preview");
// The fixture owns these host regions. Production must use its existing focus/portal owner.
const hostRegions = [...document.querySelectorAll(".host-header,.host-controls,.host-workspace")].map(
  element => [element, element.inert],
);
const mobileViewport = matchMedia(MOBILE_QUERY);
function syncFullscreen() {
  const full = mobileViewport.matches && !preview.hasAttribute("data-collapsed");
  for (const [element, previous] of hostRegions) element.inert = full || previous;
  const frame = preview.shadowRoot.querySelector(".overlay-frame");
  frame.setAttribute("role", full ? "dialog" : "region");
  if (full) {
    frame.setAttribute("aria-modal", "true");
    if (document.activeElement !== preview) preview.shadowRoot.querySelector("#close").focus();
  } else frame.removeAttribute("aria-modal");
}
preview.addEventListener("preview-placement", syncFullscreen);
mobileViewport.addEventListener("change", syncFullscreen);
syncFullscreen();
document.querySelector("#panel-width").onchange = e =>
  (preview.style.width = `min(${e.target.value}px, calc(100vw - 32px))`);
document.querySelector("#panel-theme").onchange = e => (preview.dataset.theme = e.target.value);
document.querySelector("#host-stress").onchange = e =>
  document.body.classList.toggle("host-stress", e.target.checked);
document.querySelector("#host-button").onclick = () =>
  (document.querySelector("#host-result").textContent = "The host action still works independently.");
