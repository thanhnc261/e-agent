import { icon, paintIcons } from "./icons.js";
import { actionView, sampleReadBack } from "./action-model.js";
import { scenarios, connections } from "./fixtures.js";
const $ = (s) => document.querySelector(s);
const esc = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const icons = () => paintIcons();
const state = {
  page: "home",
  category: "All",
  scenario: null,
  scene: "review",
  expanded: false,
  minimized: true,
  host: false,
  step: 0,
  tab: "proposal",
  draft: "",
  clarification: "",
  revision: 1,
  checked: false,
  customPrompt: "",
  approvedAction: null,
  records: [],
  lastAnnouncement: "",
};
const announce = (text) => ($("#announcement").textContent = text);
const active = () => scenarios[state.scenario];
const badges = (s) =>
  s
    .map(
      (n) =>
        `<span class="system-chip">${icon("connections")}${esc(n)}${active()?.blocked && n === "People directory" ? " · unavailable" : ""}</span>`,
    )
    .join("");
function navigate(page) {
  state.page = page;
  renderPage();
}
function renderPage() {
  document.querySelectorAll("[data-page]").forEach((e) => {
    e.classList.toggle("active", e.dataset.page === state.page);
    e.setAttribute(
      "aria-current",
      e.dataset.page === state.page ? "page" : "false",
    );
  });
  $("#page-title").textContent = state.host
    ? "Customer workspace"
    : { home: "Overview", work: "My work", connections: "Connections" }[
        state.page
      ];
  $("#host-toggle").innerHTML = state.host
    ? "Back to workspace"
    : "Try inside an app ↗";
  $("#main").innerHTML = state.host
    ? hostPage()
    : state.page === "home"
      ? homePage()
      : state.page === "work"
        ? workPage()
        : connectionPage();
  icons();
}
function homePage() {
  const filtered = Object.entries(scenarios).filter(
    ([, s]) => state.category === "All" || s.category === state.category,
  );
  return `
 <section class="welcome"><div><p class="eyebrow">YOUR WORKSPACE</p><h1>Your work, connected.</h1><p class="intro">One place to turn intent into action across your enterprise. <br>Bring the context. Review the change. See the result.</p></div></section>
 <form id="intent-form" class="composer"><label class="sr-only" for="intent">Describe your task</label><textarea id="intent" rows="2" placeholder="What would you like to move forward?">${esc(state.draft)}</textarea><div class="composer-bottom"><span>${icon("shield")} You review changes before they happen</span><button class="primary" type="submit">Start a task ${icon("arrow")}</button></div></form>
 <section class="capabilities"><div class="section-heading"><div><h2>A good place to start</h2><p>Explore an example workflow, then make it your own.</p></div><span class="caption">6 example workflows</span></div><div class="filters" role="group" aria-label="Filter workflows">${["All", "Revenue", "Finance", "Service", "People", "Knowledge", "Operations"].map((c) => `<button data-filter="${c}" aria-pressed="${state.category === c}" class="${state.category === c ? "selected" : ""}">${c}</button>`).join("")}</div><div class="task-grid">${filtered.map(([id, s]) => `<button class="task-card" data-scenario="${id}"><div class="card-top"><span class="tile-icon ${id}">${icon(s.icon)}</span><span class="caption">${s.category}</span>${icon("arrow")}</div><h3>${s.title}</h3><p>${s.description}</p><span class="card-bottom">${s.blocked ? "Setup needed" : s.systems.slice(0, 2).join(" + ")}</span></button>`).join("")}</div></section>
 <section class="recent-work"><div class="section-heading"><h2>Pick up where you left off</h2><button class="text-button" data-page="work">View all work ${icon("arrow")}</button></div>${workRows()}</section>`;
}
function workRows() {
  return `<div class="work-rows">${[
    ["handoff", "Needs review", "amber", "2 actions · Documents + Team chat"],
    ["knowledge", "Answer ready", "green", "Read-only · 2 sources"],
    ["service", "Needs review", "amber", "1 action · Service desk"],
  ]
    .map(
      ([id, status, color, meta]) =>
        `<button data-scenario="${id}" class="work-row"><span class="row-icon">${icon(scenarios[id].icon)}</span><span class="row-title"><strong>${scenarios[id].title}</strong><small>${meta}</small></span><span class="pill ${color}">${status}</span><span class="row-time">Sample task</span>${icon("arrow")}</button>`,
    )
    .join("")}</div>`;
}
function workPage() {
  return `<div class="page-heading"><p class="eyebrow">YOUR WORKSPACE</p><h1>Keep the work in view.</h1><p>Pick up a task with its context and decisions intact.</p></div>${workRows()}<div class="quiet-note">${icon("info")} This design study uses three fictional tasks. It is not your live work queue.</div>`;
}
function connectionPage() {
  return `<div class="page-heading"><p class="eyebrow">CONNECTIONS</p><h1>The right context.<br>The right access.</h1><p>Understand which systems a task can use and whose access it carries.</p></div><div class="connection-grid">${connections.map(([name, category, scope, status, owner], i) => `<article class="connection-card"><div class="card-top"><span class="tile-icon">${icon("connections")}</span><span class="pill ${status === "Connected" ? "green" : "neutral"}">${status}</span></div><p class="eyebrow">${category}</p><h2>${name}</h2><p>${scope}</p><details><summary>Access and data use</summary><dl><dt>Authority</dt><dd>${owner}</dd><dt>Scope</dt><dd>${scope}</dd><dt>Health</dt><dd>Simulated configuration; not probed</dd></dl></details></article>`).join("")}</div>`;
}
function hostPage() {
  return `<div class="host-heading"><div><p class="eyebrow">CUSTOMER RECORD · EXAMPLE HOST APP</p><h1>Meridian</h1><p>Customer launch · APAC team</p></div><span class="pill green">Closed won</span></div><div class="host-tabs"><span class="selected">Overview</span><span>Activity</span><span>Documents</span></div><div class="host-grid"><article class="host-card"><h2>A shared starting point</h2><p>The agreement is signed. Bring the scope, owners, and next steps together for the delivery team.</p><button class="primary" data-scenario="handoff">${icon("handoff")} Prepare delivery handoff</button></article><article class="host-card"><h2>Opportunity details</h2><dl><dt>Account owner</dt><dd>Alex Morgan</dd><dt>Signed scope</dt><dd>Revision 4</dd><dt>Target kickoff</dt><dd>19 October 2026</dd><dt>Delivery team</dt><dd>8 internal members</dd></dl></article><article class="host-card host-activity"><h2>Recent activity</h2><div class="activity-item">${icon("check")}<div><strong>Scope signed</strong><p>The customer approved revision 4.</p></div></div><div class="activity-item">${icon("file")}<div><strong>Delivery checklist attached</strong><p>Current onboarding requirements are available.</p></div></div></article></div>`;
}
function openScenario(id) {
  if (!scenarios[id]) return;
  state.scenario = id;
  state.approvedAction = null;
  state.records = [];
  state.scene = scenarios[id].readOnly ? "done" : "review";
  state.step = 0;
  state.tab = "proposal";
  state.revision = 1;
  state.checked = false;
  state.minimized = false;
  state.expanded = false;
  renderAgent();
  $("#minimize").focus();
}
function status() {
  if (active()?.blocked) return ["Setup needed", "neutral"];
  if (active()?.readOnly) return ["Answer ready", "green"];
  return {
    review: ["Needs review", "amber"],
    working: ["Working", "violet"],
    clarify: ["Needs your input", "amber"],
    verifying: ["Verifying outcome", "violet"],
    done: ["Verified", "green"],
    unknown: ["Outcome unknown", "amber"],
    stale: ["Review outdated", "amber"],
    rejected: ["Not approved", "neutral"],
  }[state.scene];
}
function renderAgent() {
  if (!state.scenario) return;
  const s = active(),
    [label, color] = status();
  $("#agent").hidden = state.minimized;
  $("#launcher").hidden = !state.minimized;
  $("#agent").classList.toggle("expanded", state.expanded);
  $("#expand").setAttribute(
    "aria-label",
    state.expanded ? "Compact assistant" : "Expand assistant",
  );
  $("#agent-subtitle").textContent = s.short;
  $("#agent-status").textContent = label;
  $("#agent-status").className = `pill ${color}`;
  $("#launcher-status").textContent = `${s.short} · ${label}`;
  const allowed = s.blocked
    ? ["blocked"]
    : s.readOnly
      ? ["done"]
      : [
          "review",
          "working",
          ...(state.scenario === "handoff" ? ["clarify"] : []),
          "verifying",
          "done",
          "unknown",
          "stale",
          "rejected",
        ];
  for (const option of $("#scene").options)
    option.hidden = !allowed.includes(option.value);
  $("#scene").disabled = s.blocked || s.readOnly;
  $("#scene").value = s.blocked ? "blocked" : state.scene;
  $("#agent-body").innerHTML =
    `<div class="task-main"><div class="context-strip">${badges(s.systems)}</div><details class="request-summary"><summary>Your request <span>${esc(s.short)}</span></summary><p>${esc(state.customPrompt || s.prompt)}</p></details>${taskContent(s)}</div><aside class="context-rail">${contextRail(s)}</aside>`;
  $("#agent-footer").innerHTML = footer(s);
  icons();
  const announcement = `${s.short}: ${label}.`;
  if (announcement !== state.lastAnnouncement) {
    announce(announcement);
    state.lastAnnouncement = announcement;
  }
}
function taskContent(s) {
  if (s.blocked)
    return `<div class="agent-message"><span class="mark small">e</span><div><h2>One connection is missing.</h2><p>I can help prepare the plan after access to the People directory is set up. No employee records have been read.</p></div></div><div class="notice"><strong>People directory · not connected</strong><p>Ask your administrator to enable the connection for your workspace. Your request stays here.</p></div>`;
  if (state.scene === "working")
    return `<div class="agent-message"><span class="mark small">e</span><div><h2>Gathering the right context</h2><p>Checking the source records before preparing a proposal. No changes have been made.</p></div></div>${activity(s, true)}`;
  if (state.scene === "clarify")
    return `<div class="agent-message"><span class="mark small">e</span><div><h2>Who should have access?</h2><p>The project team and the wider delivery group have different access. Choose the intended audience before I prepare the proposal.</p></div></div><form id="clarify-form" class="clarification"><label for="audience">Audience</label><select id="audience"><option>Delivery team only</option><option>Project owner only</option></select><button class="primary">Continue with this audience ${icon("arrow")}</button></form>`;
  if (state.scene === "unknown")
    return `<div class="agent-message"><span class="mark small">e</span><div><h2>The result is not confirmed.</h2><p>The system stopped responding after the action was sent. It may have completed. Sending it again could create a duplicate.</p></div></div><div class="notice"><strong>${state.step ? "Document verified. Message outcome unknown." : "External action outcome unknown."}</strong><p>${state.checked ? "A read-back was simulated. The result is still unresolved; an operator needs to investigate." : "Check the existing action before taking another step."}</p></div>${artifact(s)}`;
  if (state.scene === "stale")
    return `<div class="agent-message"><span class="mark small">e</span><div><h2>A source changed after this review.</h2><p>This proposal cannot be approved. Prepare a fresh revision and review the updated terms.</p></div></div><div class="notice"><strong>Source revision changed</strong><p>Recorded revision 4 → current revision 5</p></div>${artifact(s)}`;
  if (state.scene === "rejected")
    return `<div class="result-icon neutral">${icon("minus")}</div><h2>Proposal not approved</h2><p>No action was sent. You can return to the proposal to review it again.</p>`;
  if (state.scene === "verifying")
    return `<div class="agent-message"><span class="mark small">e</span><div><h2>The action was sent. Checking the result.</h2><p>Approval is recorded for this action. A separate read-back is needed before we can call it verified.</p></div></div>${activity(s, true)}<div class="quiet-note">${icon("info")} Verification is a separate step from approval.</div>`;
  if (state.scene === "done" && !s.readOnly) {
    const records = state.records.length
      ? state.records
      : [sampleReadBack(actionView(s, state))];
    return `<div class="result-icon">${icon("check")}</div><p class="eyebrow">INDEPENDENT READ-BACK COMPLETE · SAMPLE</p><h2 class="result-title">${state.step ? "The handoff is ready." : "The result is verified."}</h2><p>Each result below was checked against its own approved terms.</p>${records.map(({ action: a }) => `<div class="result-card">${icon("file")}<div><strong>${esc(a.title)}</strong><small>Example result · ${esc(a.recordId)}</small></div><span class="pill green">Verified</span></div>`).join("")}<button class="text-button" data-action="evidence">Inspect verification evidence ${icon("arrow")}</button>`;
  }
  return `<div class="agent-message"><span class="mark small">e</span><div><p>${state.step ? "The document was created and verified. Review the message separately before it is posted." : s.intro}</p><button class="source-link" data-action="evidence">${icon("book")} ${s.sources.length} sources · inspect context</button></div></div><div class="task-tabs" role="group" aria-label="Task detail">${["proposal", "activity", "sources"].map((t) => `<button data-tab="${t}" aria-pressed="${state.tab === t}" class="${state.tab === t ? "selected" : ""}">${t === "proposal" ? (s.readOnly ? "Answer" : "Proposal") : t[0].toUpperCase() + t.slice(1)}</button>`).join("")}</div>${state.tab === "activity" ? activity(s) : state.tab === "sources" ? sources(s) : artifact(s)}`;
}
function termList(fields, className = "terms") {
  return `<dl class="${className}">${fields.map(([key, value]) => `<div><dt>${esc(key)}</dt><dd>${esc(value)}</dd></div>`).join("")}</dl>`;
}
function actionMetadata(a) {
  return termList(
    [
      ["Action", a.action],
      ["Destination", a.destination],
      ["Audience / scope", a.scope],
      ["Acting identity", a.identity],
      ["Connection", a.connection],
      ["Workspace", a.workspace],
      ["Revision", a.revision],
    ],
    "terms exact-action",
  );
}
function artifact(s) {
  const a = actionView(s, state);
  const dispatched = state.scene === "unknown";
  const label = s.readOnly
    ? "Read-only"
    : dispatched
      ? "Sent · unresolved"
      : state.scene === "stale"
        ? "Outdated"
        : "Draft";
  return `<article class="artifact"><div class="artifact-top"><span class="tile-icon">${icon(state.step ? "chat" : s.readOnly ? "book" : "file")}</span><div><p class="eyebrow">${s.readOnly ? "SOURCE-GROUNDED ANSWER" : dispatched ? "DISPATCHED ACTION" : s.next ? `ACTION ${state.step + 1} OF 2` : "PROPOSED ACTION"} · V${a.revision}</p><h2>${esc(a.title)}</h2></div><span class="mini-label">${label}</span></div><p class="artifact-summary">${esc(dispatched ? "This action was sent. Its external result is unresolved." : state.step ? "Review this message as a separate action." : s.summary)}</p>${!s.readOnly ? `<div class="scope-line">${icon("shield")}<div><strong>${esc(a.destination)}</strong><small>${esc(a.scope)} · this action only</small><small>${esc(a.disclosure)}</small></div></div>` : ""}${termList(a.fields)}<div class="document-preview"><p class="document-eyebrow">${esc(state.step ? a.destination : s.category.toUpperCase())}</p><h3>${esc(a.body)}</h3><p>${esc(a.text)}</p></div><details class="technical"><summary>Exact action &amp; audit details</summary>${actionMetadata(a)}<p>Source revisions: ${a.sources.map(esc).join("; ")}</p></details></article>`;
}
function verificationEvidence() {
  const records = state.records.length
    ? state.records
    : [sampleReadBack(actionView(active(), state))];
  return `<p>Fictional read-back records. These illustrate verification evidence, not live results.</p>${records
    .map(
      ({ action: a, observedAt, verifier, outcome }) =>
        `<article class="verification-record"><h3>${esc(a.title)}</h3>${termList(
          [
            ["Observed record", a.recordId],
            ["Read-back time", observedAt],
            ["Verifier", verifier],
            ["Check result", outcome],
          ],
          "terms",
        )}${actionMetadata(a)}<h3>Observed material values</h3>${termList(a.fields)}<p>${esc(a.text)}</p></article>`,
    )
    .join("")}`;
}
function sources(s) {
  return `<div class="sources-list">${s.sources.map(([title, meta, excerpt], i) => `<button class="source-card" data-source="${i}">${icon("file")}<span><strong>${title}</strong><small>${meta}</small><p>${excerpt}</p></span>${icon("arrow")}</button>`).join("")}</div>`;
}
function activity(s, inProgress = false) {
  return `<ol class="activity-list"><li><span class="activity-dot complete">✓</span><div><strong>Context loaded</strong><p>${s.sources.length} sample sources, with recorded revisions</p></div></li><li><span class="activity-dot complete">✓</span><div><strong>Scope checked</strong><p>Only the task’s stated audience and destination</p></div></li><li><span class="activity-dot ${inProgress ? "current" : "complete"}">${inProgress ? "·" : "✓"}</span><div><strong>${state.scene === "verifying" ? "Reading back the result" : inProgress ? "Preparing the proposal" : "Proposal ready"}</strong><p>${inProgress ? "No further action is needed from you yet" : "Waiting for your explicit approval"}</p></div></li></ol>`;
}
function contextRail(s) {
  if (s.blocked)
    return `<p class="eyebrow">TASK CONTEXT</p><h3>Access comes first</h3><p>Connection setup and credential grants belong to the workspace administrator.</p>`;
  return `<p class="eyebrow">TASK CONTEXT</p><h3>Grounded in your work</h3><p class="rail-copy">The information behind this proposal, close to the decision.</p><div class="rail-sources">${s.sources.map(([title, meta], i) => `<button data-source="${i}"><span class="source-number">${i + 1}</span><span><strong>${title}</strong><small>${meta}</small></span>${icon("arrow")}</button>`).join("")}</div><div class="boundary"><span class="tile-icon">${icon("shield")}</span><h3>You control the change</h3><p>${s.readOnly ? "This task reads information only." : state.scene === "done" ? "Each completed action has a separate sample read-back record." : state.scene === "unknown" ? "The result is unresolved. Check the existing effect before another action." : state.step ? "The document is verified. This review covers only the message." : s.next ? "Create the document first. Posting the message needs its own approval." : "The action is limited to the destination and terms shown."}</p></div><details class="rail-details"><summary>Activity</summary>${activity(s)}</details>`;
}
function footer(s) {
  if (s.blocked)
    return `<span class="footer-hint">Your request is preserved.</span><button class="secondary" data-action="connections">View connections ${icon("arrow")}</button>`;
  if (state.scene === "unknown")
    return `<span class="footer-hint">${icon("info")} Do not resend an uncertain action.</span><button class="secondary" data-action="${state.checked ? "recovery-details" : "reconcile"}">${icon(state.checked ? "info" : "search")} ${state.checked ? "View recovery details" : "Check existing result"}</button>`;
  if (state.scene === "stale")
    return `<span class="footer-hint">Approval is blocked for this revision.</span><button class="primary" data-action="refresh">Prepare a fresh review</button>`;
  if (state.scene === "done" || s.readOnly)
    return `<span class="footer-hint">${icon("check")} ${s.readOnly ? "No changes made" : "Sample result independently checked"}</span><button class="secondary" data-action="minimize">Done</button>`;
  if (state.scene === "verifying")
    return `<span class="footer-hint">Checking the committed effect.</span><button class="secondary" data-action="advance">Simulate read-back ${icon("arrow")}</button>`;
  if (state.scene === "working")
    return `<span class="footer-hint">You can leave and return to this task.</span><button class="secondary" data-action="stop">Stop task</button>`;
  if (state.scene === "clarify")
    return `<span class="footer-hint">Nothing changes until you review the proposal.</span>`;
  if (state.scene === "rejected")
    return `<span class="footer-hint">No changes made.</span><button class="secondary" data-action="refresh">Return to review</button>`;
  return `<div class="footer-copy"><span class="review-indicator">${icon("shield")} ${state.step ? "Review 2 of 2" : s.next ? "Review 1 of 2" : "Your decision"}</span><small>Exact action · revision ${state.revision}</small></div><div class="footer-buttons"><button class="text-button" data-action="reject">Reject</button><button class="primary" data-action="approve">Review &amp; approve ${icon("arrow")}</button></div>`;
}
let focusBeforeDialog;
function dialog(title, body, buttons) {
  $("#modal").dataset.picker = "false";
  if (!$("#modal").open) focusBeforeDialog = document.activeElement;
  $("#modal-content").innerHTML =
    `<div class="dialog-heading"><span class="tile-icon">${icon("shield")}</span><button class="icon-button" data-action="close-dialog" aria-label="Close dialog">${icon("close")}</button></div><h2 id="modal-title" tabindex="-1">${title}</h2>${body}<div class="dialog-actions">${buttons}</div>`;
  $("#modal").showModal();
  $("#modal-title").focus();
}
function closeDialog() {
  $("#modal").close();
  focusBeforeDialog?.focus();
}
function approve() {
  if (state.scene !== "review" || active().blocked || active().readOnly) return;
  if (state.tab !== "proposal") {
    state.tab = "proposal";
    renderAgent();
    announce("Review the exact proposal before approving.");
    return;
  }
  const a = actionView(active(), state);
  dialog(
    "Approve this exact change?",
    `<p>This approval applies only to the following action and content.</p><h3>${esc(a.title)}</h3>${actionMetadata(a)}<h3>Material values</h3>${termList(a.fields)}<p>${esc(a.disclosure)}</p><div class="document-preview"><h3>${esc(a.body)}</h3><p>${esc(a.text)}</p></div>`,
    `<button class="secondary" data-action="close-dialog">Back to review</button><button class="primary" data-action="confirm">Approve this action</button>`,
  );
}
function minimize() {
  state.minimized = true;
  renderAgent();
  $("#launcher").focus();
}
document.addEventListener("click", (event) => {
  if (event.target.closest(".brand")) {
    event.preventDefault();
    state.host = false;
    navigate("home");
    return;
  }
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.page) {
    state.host = false;
    navigate(button.dataset.page);
    return;
  }
  if (button.dataset.scenario) {
    const fromComposer =
      $("#modal").open && $("#modal").dataset.picker === "true";
    state.customPrompt = fromComposer ? state.draft : "";
    state.clarification = "";
    if ($("#modal").open) closeDialog();
    openScenario(button.dataset.scenario);
    return;
  }
  if (button.dataset.filter) {
    state.category = button.dataset.filter;
    renderPage();
    document.querySelector(`[data-filter="${state.category}"]`).focus();
    return;
  }
  if (button.dataset.tab) {
    state.tab = button.dataset.tab;
    renderAgent();
    document.querySelector(`[data-tab="${state.tab}"]`).focus();
    return;
  }
  if (button.dataset.source !== undefined) {
    const [title, meta, text] = active().sources[Number(button.dataset.source)];
    dialog(
      esc(title),
      `<p class="caption">${esc(meta)} · fictional source</p><blockquote>${esc(text)}</blockquote><p>Only the excerpt relevant to this task is included in the preview.</p>`,
      `<button class="secondary" data-action="close-dialog">Back to task</button>`,
    );
    return;
  }
  const a = button.dataset.action;
  if (a === "theme") {
    document.body.classList.toggle("dark");
    return;
  }
  if (a === "host") {
    state.host = !state.host;
    renderPage();
    return;
  }
  if (a === "new") {
    state.host = false;
    state.page = "home";
    state.draft = "";
    if (state.scenario) minimize();
    renderPage();
    $("#intent").focus();
    return;
  }
  if (a === "reset") {
    location.reload();
    return;
  }
  if (a === "connections") {
    minimize();
    state.host = false;
    navigate("connections");
    return;
  }
  if (a === "minimize" || button.id === "minimize") {
    minimize();
    return;
  }
  if (button.id === "launcher") {
    state.minimized = false;
    renderAgent();
    $("#minimize").focus();
    return;
  }
  if (button.id === "expand") {
    state.expanded = !state.expanded;
    renderAgent();
    $("#expand").focus();
    return;
  }
  if (a === "close-dialog") {
    closeDialog();
    return;
  }
  if (a === "approve") {
    approve();
    return;
  }
  if (a === "confirm") {
    state.approvedAction = structuredClone(actionView(active(), state));
    closeDialog();
    state.scene = "verifying";
    renderAgent();
    return;
  }
  if (a === "reject" || a === "stop") {
    state.scene = "rejected";
    renderAgent();
    return;
  }
  if (a === "refresh") {
    state.revision++;
    state.scene = "review";
    state.tab = "proposal";
    renderAgent();
    return;
  }
  if (a === "recovery-details") {
    dialog(
      "Recovery requires investigation",
      "<p>The sample read-back did not resolve the outcome. Keep the existing action reference for an authorized operator; do not resend it.</p>",
      '<button class="secondary" data-action="close-dialog">Back to task</button>',
    );
    return;
  }
  if (a === "reconcile") {
    state.checked = true;
    renderAgent();
    return;
  }
  if (a === "advance") {
    state.records.push(
      sampleReadBack(state.approvedAction || actionView(active(), state)),
    );
    state.approvedAction = null;
    if (active().next && state.step === 0) {
      state.step = 1;
      state.scene = "review";
      state.tab = "proposal";
    } else state.scene = "done";
    renderAgent();
    return;
  }
  if (a === "evidence") {
    dialog(
      state.scene === "done" && !active().readOnly
        ? "Independent verification records"
        : "Task sources",
      state.scene === "done" && !active().readOnly
        ? verificationEvidence()
        : sources(active()),
      `<button class="secondary" data-action="close-dialog">Back to task</button>`,
    );
    return;
  }
});
document.addEventListener("input", (event) => {
  if (event.target.id === "intent") state.draft = event.target.value;
});
document.addEventListener("submit", (event) => {
  event.preventDefault();
  if (event.target.id === "intent-form") {
    if (!state.draft.trim()) {
      $("#intent").focus();
      return;
    }
    dialog(
      "Choose a sample workflow",
      `<p>This prototype does not interpret or execute requests. Your text will be used in the example you choose.</p><div class="sample-picker">${Object.entries(
        scenarios,
      )
        .map(
          ([id, s]) =>
            `<button data-scenario="${id}" class="secondary">${icon(s.icon)}${s.short}</button>`,
        )
        .join("")}</div>`,
      `<button class="text-button" data-action="close-dialog">Back</button>`,
    );
    $("#modal").dataset.picker = "true";
  }
  if (event.target.id === "clarify-form") {
    state.clarification = $("#audience").value;
    state.scene = "review";
    renderAgent();
  }
});
$("#scene").addEventListener("change", (event) => {
  if (
    active().blocked ||
    active().readOnly ||
    (event.target.value === "clarify" && state.scenario !== "handoff")
  )
    return;
  state.scene = event.target.value;
  state.checked = false;
  state.tab = "proposal";
  state.minimized = false;
  renderAgent();
});
$("#modal").addEventListener("cancel", () =>
  requestAnimationFrame(() => focusBeforeDialog?.focus()),
);
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    !$("#modal").open &&
    !state.minimized &&
    state.scenario
  ) {
    event.preventDefault();
    minimize();
  }
  if (
    event.key.toLowerCase() === "n" &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.altKey &&
    !event.target.closest("input,textarea,select,dialog,#agent")
  ) {
    event.preventDefault();
    document.querySelector('[data-action="new"]').click();
  }
});
renderPage();
icons();
