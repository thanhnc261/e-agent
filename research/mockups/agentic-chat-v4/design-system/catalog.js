import { icon, iconPaths, logo } from "./icons.js";
import { composerMarkup, statusMarkup, statusDefinitions, bindTabKeys } from "./components.js";
const $ = s => document.querySelector(s);
const esc = v =>
  String(v).replace(
    /[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const tokens = await fetch("./design-system/generated/tokens.json").then(r => r.json());
const entry = (name, description, body, contract, full = false) =>
  `<article class="ds-entry${full ? " full" : ""}" data-component="${esc(name)}"><h3>${name}</h3><p>${description}</p><div class="ds-demo">${body}</div><code class="ds-code">${esc(contract)}</code></article>`;
const section = (id, number, title, description, body) =>
  `<section class="ds-section" id="${id}"><div class="ds-section-heading"><h2>${number} / ${title}</h2><p>${description}</p></div><div class="ds-grid">${body}</div></section>`;
const row = s => `<div class="ds-row">${s}</div>`;
const note = text => ($("#kit-announcement").textContent = text);
$("#kit-logo").innerHTML = logo();
$("#catalog").innerHTML = [
  section(
    "foundations",
    "01",
    "Foundations",
    "Values have one owner. Components consume meaning—surface, action, focus—not palette numbers.",
    entry(
      "Semantic color",
      "Theme-aware roles preserve the same hierarchy across warm light, warm dark and high contrast.",
      '<div id="swatches" class="ds-swatches"></div>',
      "color.canvas → palette.canvas | color.accent → palette.accent",
      true,
    ) +
      entry(
        "Typography",
        "System fonts, deliberate hierarchy, readable metadata. No remote font dependency.",
        `<div class="ds-type-list">${[
          ["display", "Conversation"],
          ["title", "Workspace"],
          ["lg", "Section heading"],
          ["md", "Body and controls"],
          ["xs", "Secondary text"],
          ["caption", "Metadata and labels"],
        ]
          .map(
            ([size, text]) =>
              `<div><span style="font-size:var(--ea-font-size-${size})">${text}</span><small>font.size.${size}</small></div>`,
          )
          .join("")}</div>`,
        "font.family · font.size · font.weight · font.line",
      ) +
      entry(
        "Spacing, shape & motion",
        "A bounded scale gives controls and content a consistent rhythm.",
        `<div class="ds-scale">${[4, 8, 12, 16, 24, 32, 48].map(n => `<div><i style="width:var(--ea-space-${n});height:var(--ea-space-${n})"></i>${n}</div>`).join("")}</div>${row(["sm", "md", "lg", "xl"].map(r => `<span class="secondary" style="border-radius:var(--ea-radius-${r})">${r}</span>`).join(""))}<p class="view-intro">44px standard controls · 32px compact · 24px minimum target. Motion respects reduced-motion preferences.</p>`,
        "space.* · radius.* · control.* · motion.*",
      ) +
      entry(
        "Token reference",
        "Download source JSON to change the system; generated CSS and type declarations are build outputs.",
        '<div class="ds-tokens"><table class="ds-token-table"><thead><tr><th>Token</th><th>Resolved value</th></tr></thead><tbody id="token-table"></tbody></table></div>',
        "node design-system/build.mjs | --check detects output drift",
        true,
      ),
  ),
  section(
    "identity",
    "02",
    "Identity & icons",
    "One 24-unit grid, 1.65-unit rounded stroke. Icons support labels; they never carry status alone.",
    entry(
      "Connected nodes · Warm Lagoon",
      "One shared node links four entities. Warm teal and ivory carry the same identity across integrations.",
      `<div class="ds-logo-display"><span class="brand-mark">${logo()}</span>e-agent</div>${row(["light", "dark", "mono", "wordmark"].map(n => `<a href="design-system/generated/assets/logo-${n}.svg" download>Download ${n}</a>`).join(""))}<p><a href="identity.html">Inspect identity and small sizes →</a> · <a href="overlay.html">Test the embedded foundation →</a></p>`,
      "logo() · original vector geometry · minimum 24px symbol / 32px tile",
      true,
    ) +
      entry(
        `${Object.keys(iconPaths).length} matching icons`,
        "Download individual SVGs or use the sprite. Icon-only buttons need an accessible name; decorative SVGs stay hidden from assistive technology.",
        `<div class="ds-icon-grid">${Object.keys(iconPaths)
          .map(
            name =>
              `<a class="ds-icon-tile" href="design-system/generated/assets/icons/${name}.svg" download aria-label="Download ${name} icon">${icon(name)}<span>${name}</span></a>`,
          )
          .join("")}</div>`,
        "icon(name: IconName) · size 16 / 20 / 24 · currentColor",
        true,
      ),
  ),
  section(
    "controls",
    "03",
    "Actions & selection",
    "The same shape, focus treatment and state language apply throughout the product.",
    entry(
      "Action button",
      "Primary for the next consequential step; secondary and quiet for alternatives.",
      row(
        '<button class="primary" data-notice="Primary action preview">Continue</button><button class="secondary" data-notice="Secondary action preview">Back</button><button class="quiet-button" data-notice="Quiet action preview">Cancel</button>',
      ) +
        row(
          '<button class="primary" disabled>Unavailable</button><button class="primary ds-pending" disabled aria-label="Saving, please wait">' +
            icon("spinner") +
            'Saving</button><button class="ds-button-danger" data-dialog="remove">Remove</button>',
        ),
      "variant: primary | secondary | quiet | destructive · disabled | pending",
    ) +
      entry(
        "Icon button & tooltip",
        "Accessible name on the button. Tooltip is supplementary and dismisses with Escape.",
        row(
          `<span class="ds-tooltip"><button class="icon-button" aria-label="Copy reference" aria-describedby="copy-tip" data-notice="Sample reference copied visually; clipboard unchanged">${icon("copy")}</button><span role="tooltip" id="copy-tip">Copy reference</span></span><button class="icon-button" aria-label="Download sample" data-download>${icon("download")}</button><button class="icon-button" aria-label="Unavailable edit" disabled>${icon("edit")}</button>`,
        ),
        "aria-label required · focus-visible · disabled · tooltip on focus/hover",
      ) +
      entry(
        "Status badge",
        "Text and distinct icon accompany color. Unknown does not mean failed.",
        row(
          Object.keys(statusDefinitions)
            .map(t => statusMarkup(t))
            .join(""),
        ),
        "tone: neutral | progress | attention | verified | unknown | failed | blocked | cancelled",
        true,
      ) +
      entry(
        "Checkbox & radio",
        "Native controls retain keyboard and form semantics.",
        `<label class="ds-check"><input type="checkbox" checked>Include source excerpts</label><label class="ds-check"><input type="checkbox" disabled>Restricted source</label><fieldset><legend>Visibility</legend><label class="ds-check"><input type="radio" name="visibility" value="owner" checked>Project owner</label><label class="ds-check"><input type="radio" name="visibility" value="team">Delivery team</label></fieldset>`,
        "checked · unchecked · disabled · grouped radio name",
      ) +
      entry(
        "Switch",
        "Use for an immediate reversible preference, never approval.",
        `<button class="ds-switch" role="switch" aria-checked="false" id="activity-switch"><span class="ds-switch-track" aria-hidden="true"></span>Show activity details</button><p class="view-intro" id="switch-state">Activity details are hidden.</p>`,
        "role=switch · aria-checked · Space / Enter",
      ),
  ),
  section(
    "forms",
    "04",
    "Fields & validation",
    "A real label, useful hint and recoverable error belong to every input.",
    entry(
      "Text field",
      "Default, filled and disabled states use one input contract.",
      `<label class="ds-field"><span>Conversation title</span><input placeholder="Name this conversation" aria-describedby="title-hint"><small id="title-hint">Visible only within this sample workspace.</small></label><label class="ds-field"><span>Workspace</span><input value="Northstar" disabled></label>`,
      "label · value · description · disabled · readOnly",
    ) +
      entry(
        "Select & multiline field",
        "Native select for a short fixed list. Textarea supports long values.",
        `<label class="ds-field"><span>Audience</span><select><option>Project owner</option><option>Delivery team</option></select></label><label class="ds-field"><span>Additional context</span><textarea rows="3" placeholder="What should the reviewer know?"></textarea></label>`,
        "labelled select · wrapped textarea · focus-visible",
      ) +
      entry(
        "Inline validation",
        "An error explains how to correct the field. No credential or external connection is created.",
        `<form id="sample-form" novalidate><label class="ds-field"><span>Notification email</span><input id="sample-email" type="email" aria-describedby="email-help email-error" autocomplete="off"><small id="email-help">Example form only; nothing will be sent.</small><small class="ds-error" id="email-error" hidden>Enter an email address, such as name@example.com.</small></label><button class="secondary" type="submit">Check example</button></form><p class="view-intro" id="form-result" role="status"></p>`,
        "invalid · described error · correction retains value · status announcement",
      ) +
      entry(
        "Search & filters",
        "Filter locally without changing the underlying data or execution scope.",
        `<label class="ds-field"><span>Find a sample source</span><input id="source-search" type="search" placeholder="Search documents…"></label><div id="filtered-sources"></div>`,
        "input type=search · result count announced · empty result",
      ),
  ),
  section(
    "conversation-kit",
    "05",
    "Conversation",
    "Shared message, composer and context patterns keep the task understandable without adding permanent panels.",
    entry(
      "Message & citation",
      "Speaker identity, concise findings and inspectable sources.",
      `<article class="message user">Prepare a delivery handoff using the signed scope.</article><article class="message assistant"><div class="author">${logo()}e-agent</div><p>The draft brings scope, owner and kickoff into one brief. Review the terms before creating the document.</p><button class="source-citation" data-dialog="source"><span>1</span>Signed scope</button></article>`,
      "user | assistant · escaped content · source references from host data",
    ) +
      entry(
        "Artifact card",
        "A compact reference opens the workspace; it never approves the action.",
        `<button class="artifact-link" data-dialog="artifact">${icon("file")}<span><strong>Meridian · Delivery handoff</strong><small>Needs review · Action 1 of 2</small></span>${icon("arrow")}</button><p class="view-intro">The document and the sharing message are separate actions.</p>`,
        "title · status · action position · onOpen",
        false,
      ) +
      entry(
        "Composer & context chips",
        "This is the same composer view used by the mockup. References are removable; blank messages cannot be sent.",
        composerMarkup("kit-") +
          '<p id="composer-result" class="view-intro" role="status">Try adding context and sending a local example.</p>',
        "composerMarkup(prefix) · labelled input · controlled draft · context · send callback",
        true,
      ) +
      entry(
        "Suggested follow-up",
        "Suggestions prefill the composer and wait for the person to send.",
        row(
          '<button class="secondary" data-fill="What happens next?">What happens next? ' +
            icon("arrow") +
            '</button><button class="secondary" data-fill="Who will have access?">Who will have access? ' +
            icon("arrow") +
            "</button>",
        ),
        "onSelect → draft only · no implicit action",
      ) +
      entry(
        "Activity disclosure",
        "Show observable work, not hidden reasoning or fake progress.",
        `<details class="audit"><summary>3 recorded steps</summary><ol class="activity-list"><li>Source records read<small>Signed scope · revision 4</small></li><li>Proposal prepared<small>Revision 1 · waiting for review</small></li><li>Human decision required<small>No write has been sent</small></li></ol></details>`,
        "native details/summary · closed / open · recorded events",
      ),
  ),
  section(
    "work",
    "06",
    "Work & evidence",
    "Material values remain inspectable. Proposal sources and post-action observations have different meanings.",
    entry(
      "Material fields & scope",
      "A shared definition list for drafts, confirmations and observed results.",
      `<article class="document"><div class="document-label"><span class="overline">PROPOSED ACTION</span>${statusMarkup("attention")}</div><h1>Draft purchase order</h1><div class="scope">${icon("shield")}<div><strong>Purchasing / Draft orders</strong><br>Purchasing team · one exact action</div></div><dl class="terms"><div><dt>Supplier</dt><dd>Approved Supply Co.</dd></div><div><dt>Total</dt><dd>700.00 USD</dd></div><div><dt>Quantity</dt><dd>7 units</dd></div><div><dt>Effect</dt><dd>Create draft only</dd></div></dl></article>`,
      "fields: label/value[] · exact action version · no truncated material values",
    ) +
      entry(
        "Source & read-back evidence",
        "Input excerpts ground a proposal; observed records verify an outcome.",
        `<article class="source-item">${icon("book")}<div><strong>Supplier offer</strong><small>Input source · revision 2</small><p>100.00 USD per unit. Sample approved supplier record.</p></div></article><article class="source-item">${icon("check")}<div><strong>PO-DEMO-084</strong><small>Observed result · independent sample read-back</small><p>7 units · 700.00 USD · draft state. Fictional observation, not a live result.</p></div></article>`,
        "source revision/provenance ≠ outcome evidence · explicit missing values",
      ) +
      entry(
        "Data table & pagination",
        "Use a table when people compare records. Keep row actions labelled and overflow contained.",
        `<div class="ds-table-scroll" tabindex="0" role="region" aria-label="Sample work table"><table class="ds-table"><caption>Sample work</caption><thead><tr><th scope="col">Task</th><th scope="col">State</th><th scope="col">Owner</th></tr></thead><tbody id="work-rows"></tbody></table></div><div class="ds-row"><button class="secondary" id="previous-page" disabled>Previous</button><span id="page-count" class="view-intro">Page 1 of 2</span><button class="secondary" id="next-page">Next</button></div>`,
        "table semantics · keyboard-scrollable region · visible page position",
        true,
      ),
  ),
  section(
    "feedback",
    "07",
    "Feedback & recovery",
    "Every state explains what is known and offers a supported next step.",
    entry(
      "Loading & progress",
      "Indeterminate work uses a status label. A numeric meter needs a measured denominator.",
      `${statusMarkup("progress", "Reading sources")}<div aria-hidden="true"><div class="ds-skeleton"></div><div class="ds-skeleton"></div><div class="ds-skeleton"></div></div><label for="sample-progress" class="view-intro">2 of 3 sample files indexed</label><progress id="sample-progress" value="2" max="3">2 of 3</progress>`,
      "pending · indeterminate skeleton · measured progress · reduced motion",
    ) +
      entry(
        "Empty & no results",
        "Explain the absence and give one relevant action.",
        `<div class="ds-empty">${icon("chat")}<h3>No conversations yet</h3><p>Start with a question or describe the work you need.</p><a class="secondary" href="./">Start a conversation</a></div>`,
        "empty collection ≠ failed request ≠ access denied",
      ) +
      entry(
        "Unknown outcome",
        "Never offer a blind retry for a possibly committed write.",
        `<div class="ds-alert" data-tone="unknown">${icon("alert")}<div><strong>Result not confirmed</strong><p>The action may have completed. Check the existing result before another write.</p></div></div><button class="secondary" data-notice="Sample result remains unresolved. No action was resent.">${icon("search")}Check existing result</button>`,
        "unknown effect · preserve request · read-back / investigation",
      ) +
      entry(
        "Error & access needed",
        "Explain the affected step and preserve work.",
        `<div class="ds-alert" data-tone="failed">${icon("alert")}<div><strong>Source could not be read</strong><p>Your draft is preserved. Ask the workspace administrator to check the connection.</p></div></div>${statusMarkup("blocked", "People directory unavailable")}`,
        "failed read ≠ unknown write · actionable error · no fabricated access",
      ) +
      entry(
        "Inline notification",
        "A polite announcement supplements a visible, persistent result.",
        `<button class="secondary" id="notify-demo">Save display preference</button><div id="notification-demo" class="ds-alert" hidden role="status">${icon("check")}Display preference saved for this example.</div>`,
        "aria-live=polite · no auto-dismiss for required decisions",
        true,
      ),
  ),
  section(
    "overlays",
    "08",
    "Navigation & overlays",
    "Navigation changes placement, never execution state. Modals are reserved for bounded decisions.",
    entry(
      "Tabs",
      "Related views share a region. Arrow keys move focus and selection.",
      `<div class="ds-tabs" role="tablist" aria-label="Sample workspace"><button id="tab-draft" role="tab" aria-selected="true" aria-controls="panel-draft" data-kit-tab="draft">Draft</button><button id="tab-source" role="tab" aria-selected="false" aria-controls="panel-source" tabindex="-1" data-kit-tab="source">Sources</button></div><div class="ds-tab-panel" role="tabpanel" id="panel-draft" aria-labelledby="tab-draft" tabindex="0">The exact proposal remains available while you inspect supporting evidence.</div><div class="ds-tab-panel" role="tabpanel" id="panel-source" aria-labelledby="tab-source" tabindex="0" hidden>Signed scope · revision 4. Source inspection does not change approval.</div>`,
      "tablist / tab / tabpanel · roving tabIndex · Arrow / Home / End",
    ) +
      entry(
        "Disclosure menu",
        "For a small set of secondary actions, native disclosure is sufficient.",
        `<details class="ds-menu"><summary>${icon("more")}Conversation options</summary><div><button data-notice="Rename is a component demonstration">${icon("edit")}Rename conversation</button><button data-download>${icon("download")}Export sample text</button></div></details>`,
        "native details · in-flow expansion · Tab through actions",
      ) +
      entry(
        "Confirmation dialog",
        "Short confirmations focus Back. Long reviews focus the heading so the full context can be read before the decision.",
        `<button class="primary" data-dialog="confirm">Preview confirmation</button><p class="view-intro">The example changes local UI only. It cannot approve or send a business action.</p>`,
        "native modal dialog · labelled heading · focus return · Escape cancel",
      ) +
      entry(
        "Navigation rail & workspace",
        "Collapsed / expanded navigation and the right workspace share one conversation state.",
        `<div class="ds-row"><button class="icon-button" aria-label="Toggle navigation preview" id="rail-toggle" aria-expanded="false">${icon("panel")}</button><span id="rail-label" hidden>Conversation history</span><a class="secondary" href="./">Try full placement</a></div><p class="view-intro">The live mockup demonstrates desktop split view and mobile chat/workspace switching.</p>`,
        "layout owns geometry · controller owns task/draft · no remount on placement change",
      ),
  ),
].join("");
function paint() {
  document.querySelectorAll("[data-icon]").forEach(e => (e.innerHTML = icon(e.dataset.icon)));
}
function renderTokens() {
  const theme = $("#theme").value;
  document.documentElement.dataset.theme = theme;
  $("#open-mockup").href = `./?theme=${theme}`;
  const t = tokens[theme];
  $("#swatches").innerHTML = [
    "canvas",
    "surface",
    "surface-sunken",
    "text",
    "accent",
    "focus",
    "status-verified",
    "status-unknown",
    "status-failed",
    "status-progress",
    "border-strong",
    "message-user",
  ]
    .map(
      n =>
        `<div class="ds-swatch"><i style="background:var(--ea-color-${n})"></i><strong>${n}</strong><code>${t["color." + n]}</code></div>`,
    )
    .join("");
  $("#token-table").innerHTML = Object.entries(t)
    .map(([n, v]) => `<tr><th scope="row">${n}</th><td>${esc(v)}</td></tr>`)
    .join("");
}
$("#theme").addEventListener("change", renderTokens);
renderTokens();
paint();
let returnFocus;
function openDialog(kind) {
  returnFocus = document.activeElement;
  const title = {
    confirm: "Review the exact action",
    remove: "Remove this sample?",
    source: "Signed scope",
    artifact: "Meridian · Delivery handoff",
  }[kind];
  const body =
    kind === "confirm"
      ? '<p>Create one draft order in Purchasing / Draft orders. Purchasing team only. Acting identity: Jamie Lee (sample). Workspace: Northstar. Connection revision: 3. Proposal revision: 1.</p><dl class="terms"><div><dt>Quantity</dt><dd>7 units</dd></div><div><dt>Total</dt><dd>700.00 USD</dd></div><div><dt>Supplier</dt><dd>Approved Supply Co.</dd></div><div><dt>Effect</dt><dd>Draft only; no order sent</dd></div></dl>'
      : kind === "source"
        ? "<p>Sample document · revision 4</p><blockquote>The agreed scope covers onboarding, reporting and a guided pilot. Kickoff: 19 October.</blockquote>"
        : kind === "artifact"
          ? "<p>Sample document · Alex Morgan · kickoff 19 October. This dialog demonstrates opening an artifact; the full mockup uses the right workspace.</p>"
          : "<p>This removes only a sample item in this component demonstration. No business record is affected.</p>";
  $("#kit-dialog").innerHTML =
    `<div class="dialog-top"><h2 id="kit-dialog-title">${title}</h2></div><div class="ds-dialog-copy">${body}</div><div class="dialog-actions"><button class="secondary" id="dialog-back" data-close>Back</button>${["confirm", "remove"].includes(kind) ? '<button class="primary" data-demo-confirm>Confirm example</button>' : ""}</div>`;
  $("#kit-dialog").showModal();
  $("#dialog-back").focus();
}
function closeDialog() {
  $("#kit-dialog").close();
  returnFocus?.focus();
}
document.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.notice) note(b.dataset.notice);
  if (b.dataset.dialog) openDialog(b.dataset.dialog);
  if (b.hasAttribute("data-close")) closeDialog();
  if (b.hasAttribute("data-demo-confirm")) {
    closeDialog();
    note("Example confirmed locally. No external action executed.");
  }
  if (b.hasAttribute("data-download")) {
    const url = URL.createObjectURL(
      new Blob(["e-agent component example\nFictional data only."], { type: "text/plain" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "e-agent-example.txt";
    a.click();
    URL.revokeObjectURL(url);
  }
  if (b.dataset.fill) {
    $("#kit-prompt").value = b.dataset.fill;
    resizeComposer();
    $("#kit-prompt").focus();
  }
  if (b.dataset.kitTab) selectTab(b);
});
$("#kit-dialog").addEventListener("close", () => returnFocus?.focus());
$("#activity-switch").addEventListener("click", e => {
  const b = e.currentTarget;
  const on = b.getAttribute("aria-checked") !== "true";
  b.setAttribute("aria-checked", on);
  $("#switch-state").textContent = `Activity details are ${on ? "visible" : "hidden"}.`;
});
$("#sample-form").addEventListener("submit", e => {
  e.preventDefault();
  const input = $("#sample-email");
  const valid = input.value.trim() !== "" && input.validity.valid;
  input.setAttribute("aria-invalid", String(!valid));
  $("#email-error").hidden = valid;
  $("#form-result").textContent = valid ? "Format accepted for this local example. Nothing sent." : "";
  if (!valid) input.focus();
});
const sources = ["Signed scope", "Delivery checklist", "Supplier offer"];
function filterSources(announce = true) {
  const matches = sources.filter(n => n.toLowerCase().includes($("#source-search").value.toLowerCase()));
  $("#filtered-sources").innerHTML = matches.length
    ? matches.map(n => `<div class="source-item">${icon("file")}<strong>${n}</strong></div>`).join("")
    : '<p class="view-intro">No matching sources. Try another name.</p>';
  if (announce) note(`${matches.length} sample sources found.`);
}
$("#source-search").addEventListener("input", filterSources);
filterSources(false);
let page = 1;
function tablePage() {
  const rows =
    page === 1
      ? [
          ["Delivery handoff", "attention", "Jamie Lee"],
          ["Travel policy", "verified", "Alex Morgan"],
        ]
      : [
          ["Service request", "unknown", "Sam Chen"],
          ["Onboarding plan", "blocked", "Jamie Lee"],
        ];
  $("#work-rows").innerHTML = rows
    .map(
      ([task, status, owner]) =>
        `<tr><th scope="row">${task}</th><td>${statusMarkup(status)}</td><td>${owner}</td></tr>`,
    )
    .join("");
  $("#page-count").textContent = `Page ${page} of 2`;
  $("#previous-page").disabled = page === 1;
  $("#next-page").disabled = page === 2;
}
$("#previous-page").onclick = () => {
  page = 1;
  tablePage();
};
$("#next-page").onclick = () => {
  page = 2;
  tablePage();
};
tablePage();
const composer = $("#kit-composer"),
  prompt = $("#kit-prompt");
function resizeComposer() {
  prompt.style.height = "auto";
  prompt.style.height = Math.min(prompt.scrollHeight, 160) + "px";
  composer.querySelector(".send-button").disabled = !prompt.value.trim();
}
prompt.addEventListener("input", resizeComposer);
prompt.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    composer.requestSubmit();
  }
});
composer.addEventListener("submit", e => {
  e.preventDefault();
  if (!prompt.value.trim()) return;
  $("#composer-result").textContent = `Local example received: ${prompt.value}`;
  prompt.value = "";
  $("#kit-composer-context").hidden = true;
  $("#kit-composer-context").textContent = "";
  resizeComposer();
});
composer.querySelector("[data-action=add-context]").onclick = () => {
  const c = $("#kit-composer-context");
  c.hidden = false;
  c.innerHTML = `<span class="context-chip">${icon("file")}Sample source<button type="button" aria-label="Remove sample source">${icon("close")}</button></span>`;
  c.querySelector("button").onclick = () => {
    c.hidden = true;
    c.textContent = "";
  };
};
resizeComposer();
$("#notify-demo").onclick = () => {
  $("#notification-demo").hidden = false;
};
$("#rail-toggle").onclick = e => {
  const b = e.currentTarget;
  const on = b.getAttribute("aria-expanded") !== "true";
  b.setAttribute("aria-expanded", on);
  $("#rail-label").hidden = !on;
};
function selectTab(b) {
  document.querySelectorAll("[data-kit-tab]").forEach(t => {
    const selected = t === b;
    t.setAttribute("aria-selected", String(selected));
    t.tabIndex = selected ? 0 : -1;
    $("#" + t.getAttribute("aria-controls")).hidden = !selected;
  });
  b.focus();
}
bindTabKeys(document.querySelector(".ds-tabs"), selectTab);
document.querySelectorAll(".ds-tooltip").forEach(t => {
  t.addEventListener("keydown", e => {
    if (e.key === "Escape") t.dataset.dismissed = "true";
  });
  for (const name of ["pointerleave", "focusout"]) t.addEventListener(name, () => delete t.dataset.dismissed);
});
