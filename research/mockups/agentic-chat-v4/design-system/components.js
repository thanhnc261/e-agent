// Native prototype views shared by the mockup and catalog. Production maps to React Aria primitives.
import { icon } from "./icons.js";
export function composerMarkup(prefix = "") {
  if (!/^[a-z0-9-]*$/.test(prefix)) throw new Error("Invalid composer ID prefix");
  return `            <div class="composer-wrap">
              <form id="composer" class="composer">
                <div
                  id="composer-context"
                  class="composer-context"
                  hidden
                ></div>
                <label class="sr-only" for="prompt">Message e-agent</label
                ><textarea
                  id="prompt"
                  placeholder="Ask, explore, or get something done…"
                  rows="2"
                ></textarea>
                <div class="composer-tools">
                  <button
                    type="button"
                    class="context-button"
                    data-action="add-context"
                  >
                    <span data-icon="plus"></span>Add context</button
                  ><button
                    class="send-button"
                    type="submit"
                    aria-label="Send message"
                    disabled
                  >
                    <span>Send</span><span data-icon="send"></span>
                  </button>
                </div>
              </form>
              <p class="composer-note">
                <span class="keyboard-help"
                  >Enter to send · Shift + Enter for a new line</span
                >
                <span>Sample conversation · no live integrations</span>
              </p>
            </div>`.replace(/(id|for)="([^"]+)"/g, (_, attr, id) => `${attr}="${prefix}${id}"`);
}
export const statusDefinitions = {
  neutral: { label: "Draft", icon: "file" },
  progress: { label: "Working", icon: "clock" },
  attention: { label: "Needs review", icon: "shield" },
  verified: { label: "Verified", icon: "check" },
  unknown: { label: "Outcome unknown", icon: "alert" },
  failed: { label: "Failed", icon: "close" },
  blocked: { label: "Access needed", icon: "lock" },
  cancelled: { label: "Cancelled", icon: "stop" },
};
export function statusMarkup(tone, label = statusDefinitions[tone]?.label) {
  if (!statusDefinitions[tone]) throw Error("Unknown status");
  const safe = String(label).replace(
    /[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
  return `<span class="ds-status" data-tone="${tone}">${icon(statusDefinitions[tone].icon)}${safe}</span>`;
}

// Shared keyboard mechanics; the owning view selects and renders its own panel.
export function bindTabKeys(tablist, select) {
  tablist.addEventListener("keydown", event => {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
    const tabs = [...tablist.querySelectorAll('[role="tab"]')];
    const current = tabs.indexOf(tablist.getRootNode().activeElement);
    if (current < 0) return;
    event.preventDefault();
    const index =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    select(tabs[index]);
    tabs[index].focus();
  });
}
