// Study 05 composition. Reuses v4's design system and v3 fixtures unchanged; see README.
import { MOBILE_QUERY } from "../agentic-chat-v4/design-system/generated/metrics.js";
import { composerMarkup, statusMarkup, bindTabKeys } from "../agentic-chat-v4/design-system/components.js";
import { followupQuestions, highlights, answerFollowup } from "../agentic-chat-v4/chat-content.js";
import { icon } from "../agentic-chat-v4/design-system/icons.js";
import { scenarios, connections } from "../agentic-workspace-v3/fixtures.js";
import { actionView, sampleReadBack } from "../agentic-workspace-v3/action-model.js";
import { logo } from "./identity.js";

const isMobile = () => matchMedia(MOBILE_QUERY).matches;
const $ = s => document.querySelector(s);
$("#composer-slot").outerHTML = composerMarkup();
const esc = value =>
  String(value ?? "").replace(
    /[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

// ---- Theme: in-page choice that honours the OS preference by default (EA-12). ----
const themeParam = new URLSearchParams(location.search).get("theme");
let themeChoice = ["light", "dark", "high-contrast"].includes(themeParam) ? themeParam : "system";
const darkQuery = matchMedia("(prefers-color-scheme: dark)");
const contrastQuery = matchMedia("(prefers-contrast: more)");
function applyTheme() {
  const resolved =
    themeChoice !== "system"
      ? themeChoice
      : contrastQuery.matches
        ? "high-contrast"
        : darkQuery.matches
          ? "dark"
          : "light";
  if (resolved === "light") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = resolved;
  $("#theme").value = themeChoice;
}
darkQuery.addEventListener("change", applyTheme);
contrastQuery.addEventListener("change", applyTheme);
$("#theme").addEventListener("change", e => {
  themeChoice = e.target.value;
  applyTheme();
  announce(`Theme: ${e.target.selectedOptions[0].textContent}.`);
});

// ---- State ----
const threads = [];
let activeId = null,
  navOpen = false,
  workspaceOpen = false,
  tab = "document",
  serial = 0,
  pendingPrompt = "",
  emptyDraft = "",
  previousFocus,
  studyOpen = false;
const current = () => threads.find(t => t.id === activeId);
const scenario = () => scenarios[current()?.scenario];
const action = () => actionView(scenario(), current());

const sceneLabels = {
  working: "Working",
  "needs-input": "Needs your input",
  review: "Needs review",
  executing: "Sending approved action",
  verifying: "Committed · checking result",
  done: "Verified",
  unknown: "Outcome unknown",
  stale: "Review outdated",
  rejected: "Not approved",
  failed: "Failed · nothing created",
  stopped: "Stopped",
};
const sceneTones = {
  working: "progress",
  "needs-input": "attention",
  review: "attention",
  executing: "progress",
  verifying: "progress",
  done: "verified",
  unknown: "unknown",
  stale: "attention",
  rejected: "cancelled",
  failed: "failed",
  stopped: "cancelled",
};
const stoppable = new Set(["working", "needs-input", "executing", "verifying"]);
const noWorkspace = new Set(["working", "needs-input", "stopped"]);
const audiences = [
  ["Delivery team only", "8 internal members"],
  ["Project owner only", "Alex Morgan · direct message"],
];
const label = t => sceneLabels[t.scene];

// Consequences and reversibility are stated, never guessed (AG-APPR-1, AG-UNC-4).
function consequence(t, s, a) {
  if (t.step === 1)
    return {
      effect: `Posts one message to ${a.destination}.`,
      reversible:
        "Not reversible once delivered. The message can be deleted later, but recipients may already have read it.",
    };
  const known = {
    procurement: {
      effect: "Creates one draft purchase order. Nothing is confirmed or sent to the supplier.",
      reversible: "Reversible. The draft can be deleted before anyone confirms it.",
    },
    handoff: {
      effect: `Creates one document in ${a.destination}, visible to ${a.scope}.`,
      reversible: "Reversible. The document owner can delete it.",
    },
  }[t.scenario];
  return (
    known || {
      effect: `${a.action} in ${a.destination}.`,
      reversible:
        "The system did not state whether this can be undone. Treat it as not reversible.",
    }
  );
}

function hydrate() {
  document.querySelectorAll("button[aria-label]").forEach(e => {
    if (!e.textContent.trim()) e.title = e.getAttribute("aria-label");
  });
  document.querySelectorAll("[data-icon]").forEach(e => (e.innerHTML = icon(e.dataset.icon)));
  document.querySelectorAll("[data-logo]").forEach(e => (e.innerHTML = logo()));
}
function announce(text) {
  $("#announce").textContent = text;
}
function saveDraft() {
  if (current()) current().draft = $("#prompt").value;
  else emptyDraft = $("#prompt").value;
}
function setNav(open) {
  const focused = document.activeElement;
  navOpen = open;
  $("#app").classList.toggle("nav-open", open);
  $(".scrim").hidden = !open;
  document
    .querySelectorAll("button[data-action=nav]")
    .forEach(button => button.setAttribute("aria-expanded", String(open)));
  $(".main").inert = open && isMobile();
  if (open || $("#sidebar").contains(focused)) {
    (open ? $(".expanded-toggle") : isMobile() ? $(".mobile-nav") : $(".collapsed-toggle")).focus();
  }
}
function historyNote(t) {
  const s = scenarios[t.scenario];
  if (s.blocked) return "Needs access";
  if (s.readOnly) return t.scene === "working" ? "Working" : "Read-only answer";
  return label(t);
}
function renderHistory() {
  $("#history").innerHTML = threads
    .map(
      t =>
        `<button data-thread="${t.id}" class="${t.id === activeId ? "selected" : ""}" ${t.id === activeId ? 'aria-current="true"' : ""}>${esc(scenarios[t.scenario].short)}<small>${esc(historyNote(t))}</small></button>`,
    )
    .join("");
  $("#empty-history").hidden = threads.length > 0;
}
function renderStatus() {
  const t = current();
  if (!t || scenario().blocked) {
    $("#run-status").innerHTML = "";
    return;
  }
  const readOnlyDone = scenario().readOnly && t.scene === "done";
  const status = readOnlyDone ? statusMarkup("neutral", "Read-only answer") : statusMarkup(sceneTones[t.scene], label(t));
  const stop = stoppable.has(t.scene)
    ? `<button class="stop-button" data-action="stop">${icon("stop")}Stop</button>`
    : "";
  $("#run-status").innerHTML = status + stop;
}
function setWorkspace(open) {
  const t = current();
  workspaceOpen = open && !!t && !scenario().blocked && !noWorkspace.has(t.scene);
  $("#workspace").hidden = !workspaceOpen;
  $("#surface").classList.toggle("has-workspace", workspaceOpen);
  $("#reopen").hidden = !t || scenario().blocked || workspaceOpen || noWorkspace.has(t.scene);
  if (t) t.workspaceOpen = workspaceOpen;
  if (workspaceOpen) renderWorkspace();
}
function render() {
  const t = current();
  $("#surface").classList.toggle("empty", !t);
  $("#conversation-title").textContent = t ? scenario().short : "New conversation";
  $("#messages").innerHTML = t ? conversation() : welcome();
  $("#prompt").value = t ? t.draft : emptyDraft;
  $("#prompt").placeholder = t
    ? "Ask about this work, or describe a change…"
    : "Describe the work you need help with…";
  renderComposer();
  renderHistory();
  renderStatus();
  setWorkspace(workspaceOpen);
  renderStudy();
  hydrate();
}
function welcome() {
  return `<div class="welcome"><div class="welcome-mark">${logo()}</div><h1>What shall we<br>move forward?</h1><p>Bring a question. Untangle a problem.<br>Turn a conversation into work, together.</p><div class="starters"><button data-start="handoff">${icon("file")}Prepare a handoff</button><button data-start="knowledge">${icon("search")}Find an answer</button><button data-start="procurement">${icon("purchase")}Draft an order</button></div><section class="disclosure" aria-labelledby="disclosure-title"><h2 id="disclosure-title">You are working with e-agent, an AI agent</h2><p>It reads the sources you can access, prepares proposals and explains them with citations. It can make mistakes, so check what it shows you.</p><ul><li><strong>Can:</strong> answer from connected sources, draft documents, messages and purchase drafts.</li><li><strong>Cannot:</strong> send or change anything without your approval of the exact action, or choose which account it acts as.</li><li><strong>Always:</strong> you can stop it, reject a proposal, and see whether a result was independently verified.</li></ul><p>This study uses fictional sample data and does not call a model.</p></section></div>`;
}
function artifactLink() {
  const t = current(),
    s = scenario();
  return `<button class="artifact-link" data-action="workspace">${icon(t.step ? "chat" : s.readOnly ? "book" : "file")}<span><strong>${esc(action().title)}</strong><small>${s.readOnly ? "Read-only · 2 sources" : label(t) + " · " + (t.step ? "Action 2 of 2" : s.next ? "Action 1 of 2" : "One action")} · Open workspace</small></span>${icon("arrow")}</button>`;
}
function milestones() {
  const s = scenario();
  const steps = [
    ["Request received", true],
    [`Reading ${s.sources.length} sample sources`, true],
    [s.readOnly ? "Preparing an answer" : "Preparing a proposal", false],
  ];
  return `<ol class="milestones" aria-label="Recorded activity">${steps
    .map(
      ([text, done]) =>
        `<li data-done="${done}">${icon(done ? "check" : "clock")}${esc(text)}${done ? "" : " · not finished"}</li>`,
    )
    .join("")}</ol>`;
}
function conversation() {
  const t = current(),
    s = scenario();
  let reply;
  if (s.blocked)
    reply =
      '<p>I need access to the people directory before I can prepare a plan for this teammate. No employee records have been read.</p><button class="secondary" data-action="connections">View connections</button>';
  else if (t.scene === "working")
    reply = `<p>Working on your request. These are the recorded steps so far:</p>${milestones()}<p class="view-intro">You can stop at any time. Nothing has been proposed or sent yet.</p>`;
  else if (t.scene === "needs-input")
    reply = `<p>Before I draft the handoff, one question: <strong>who should receive it?</strong> The project brief names both the delivery team and the project owner, so I won’t guess.</p><div class="choice-list" role="group" aria-label="Choose the audience">${audiences.map(([name, note]) => `<button data-audience="${esc(name)}">${esc(name)}<small>${esc(note)} · sample</small></button>`).join("")}</div><p class="view-intro">You can also answer in your own words below. Your request stays as written.</p>`;
  else if (t.scene === "stopped")
    reply = `<p>Stopped at your request. ${t.stoppedNote || "Nothing was proposed or sent, so there is nothing to undo."}</p><button class="secondary" data-action="restart">Start this request again</button>`;
  else if (s.readOnly)
    reply = `<p>${esc(s.intro)}</p><p>The regional limit depends on the employee’s region, which is not included here. Check that before making a booking.</p>${artifactLink()}`;
  else if (t.scene === "executing")
    reply = `<p>You approved the exact action. It is being sent to ${esc(action().destination)} now. It is not complete or verified yet.</p>${artifactLink()}`;
  else if (t.scene === "failed")
    reply = `<p>The approved action failed. <strong>Nothing was created.</strong> Purchasing reported that the target record was locked (sample error). You can review the proposal again; it will need a new approval.</p>${artifactLink()}`;
  else if (t.scene === "unknown")
    reply = `<p>${t.stoppedNote || "The request was sent, but its result is still unknown. It may have completed."}</p><div class="inline-notice">${t.checked ? "The sample check is still unresolved. An operator needs to investigate." : "I won’t resend it. Check the existing action before deciding what happens next."}</div>${artifactLink()}`;
  else if (t.scene === "stale")
    reply = `<p>A source changed after the draft was prepared (${esc(s.sources[0][0])}). This revision can no longer be approved.</p>${artifactLink()}`;
  else if (t.scene === "rejected")
    reply = `<p>You rejected this proposal. No action was sent for this revision. Earlier completed actions remain unchanged.</p>${artifactLink()}`;
  else if (t.scene === "verifying")
    reply = `<p>The system recorded the action as committed. An independent check of its result is running; approval and commit are not verification.</p>${artifactLink()}`;
  else if (t.scene === "done")
    reply = `<p>${s.next ? "The document and message have separate sample read-back records." : "The sample result matches the approved action."}</p>${artifactLink()}`;
  else
    reply = `<details class="source-trace"><summary>${icon("check")}Checked ${s.sources.length} sample sources ${icon("chevron")}</summary><div>${sourceLinks()}</div></details><p>${t.step ? "The document has been created and checked in this example. The message is a separate action for you to review." : esc(s.intro)}</p>${chatHighlights()}${artifactLink()}<p class="view-intro">${t.step ? "Only this message is awaiting approval." : s.next ? "I’ll create the document first. Sharing the message will need a separate approval." : "Review the proposed change in the workspace before approving."}</p>`;
  return `<article class="message user">${esc(t.prompt)}</article><article class="message assistant"><div class="author">${logo()}e-agent <span>AI agent · sample response</span></div>${reply}</article>${t.followups.map(f => `<article class="message user">${esc(f.prompt)}${f.context.length ? `<div class="sent-context">${f.context.map(i => `${icon("file")} ${esc(s.sources[i][0])}`).join(" · ")}</div>` : ""}</article><article class="message assistant"><div class="author">${logo()}e-agent <span>AI agent · sample response</span></div><p>${esc(f.answer)}</p>${f.prompt === followupQuestions[0] && !s.blocked ? `<div class="source-links">${sourceLinks()}</div>` : ""}</article>`).join("")}${noWorkspace.has(t.scene) ? "" : `<div class="followup-suggestions" aria-label="Suggested follow-ups"><span>Continue the conversation</span>${followupQuestions
    .slice(0, 2)
    .map(q => `<button data-suggest="${esc(q)}">${esc(q)} ${icon("arrow")}</button>`)
    .join("")}</div>`}`;
}
function sourceLinks() {
  return (scenario().sources || [])
    .map(
      ([name], i) =>
        `<button class="source-citation" data-inspect-source="${i}"><span>${i + 1}</span>${esc(name)}</button>`,
    )
    .join("");
}
function chatHighlights() {
  return `<ul class="chat-highlights">${highlights(scenario(), action())
    .map(([name, value]) => `<li><span>${esc(name)}</span><strong>${esc(value)}</strong></li>`)
    .join("")}</ul>`;
}
function renderComposer() {
  const t = current();
  const context = t?.context || [];
  const canAdd = t && !scenario().blocked;
  $('#composer [data-action="add-context"]').innerHTML = canAdd
    ? `${icon("plus")}Add context`
    : `${icon("connections")}Work context`;
  $("#composer-context").hidden = !context.length;
  $("#composer-context").innerHTML = context
    .map(
      i =>
        `<span class="context-chip">${icon("file")}${esc(scenario().sources[i][0])}<button type="button" data-remove-context="${i}" aria-label="Remove ${esc(scenario().sources[i][0])}">${icon("close")}</button></span>`,
    )
    .join("");
  sizeComposer();
}
function sizeComposer() {
  const input = $("#prompt");
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
  $(".send-button").disabled = !input.value.trim();
}
function addContext() {
  if (!current() || scenario().blocked) {
    showConnections();
    return;
  }
  dialog(
    "Add a reference",
    `<p>Include a sample source with your next message. This does not change the proposal or grant access.</p><div class="choice-list">${scenario()
      .sources.map(
        ([name, revision], i) =>
          `<button data-add-context="${i}" ${current().context.includes(i) ? "disabled" : ""}>${esc(name)}<small>${esc(revision)}${current().context.includes(i) ? " · already included" : ""}</small></button>`,
      )
      .join("")}</div>`,
  );
}
function terms(fields) {
  return `<dl class="terms">${fields.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>`;
}
function metadata(a) {
  return terms([
    ["Operation", a.action],
    ["Destination", a.destination],
    ["Audience", a.scope],
    ["Acting identity", a.identity],
    ["Workspace", a.workspace],
    ["Connection", a.connection],
    ["Proposal revision", a.revision],
  ]);
}
function consequenceBlock() {
  const c = consequence(current(), scenario(), action());
  return `<section class="consequence" aria-label="What happens if you approve"><h2>What happens if you approve</h2><p>${esc(c.effect)}</p><p><strong>${esc(c.reversible)}</strong></p></section>`;
}
function acting(a) {
  return `<dl class="acting"><dt>Acts as</dt><dd>${esc(a.identity)}</dd><dt>Connection</dt><dd>${esc(a.connection)}</dd></dl>`;
}
function documentView() {
  const t = current(),
    s = scenario(),
    a = action();
  const tone = s.readOnly ? "neutral" : sceneTones[t.scene];
  const statusText = s.readOnly ? "Read-only" : t.scene === "unknown" ? "Sent · unresolved" : label(t);
  return `<article class="document"><div class="document-label"><span class="overline">${s.readOnly ? "KNOWLEDGE" : t.step ? "MESSAGE" : s.category.toUpperCase()} / ${s.readOnly ? "REFERENCE" : `REVISION ${t.revision}`}</span>${statusMarkup(tone, statusText)}</div><p><span class="ai-origin">${logo()}Drafted by e-agent · sample</span></p><h1>${esc(a.title)}</h1><p class="lede">${esc(t.step ? "A separate message for your review." : s.summary)}</p>${!s.readOnly ? `<div class="scope">${icon("shield")}<div><strong>${esc(a.destination)}</strong><br>${esc(a.scope)} · this action only</div></div>${s.next && t.scene === "review" ? `<p><button class="quiet-button" data-action="audience">${icon("edit")}Change audience</button></p>` : ""}${acting(a)}${consequenceBlock()}` : ""}${terms(a.fields)}<div class="document-copy"><h2>${esc(a.body)}</h2><p>${esc(a.text)}</p></div><details class="audit"><summary>${s.readOnly ? "Reference details" : "Full action record and source revisions"}</summary>${metadata(a)}<p>${esc(a.disclosure)}</p><p>Source revisions: ${a.sources.map(esc).join("; ")}</p></details></article>`;
}
function sourcesView() {
  return `<h2 class="view-heading">Sources behind the work</h2><p class="view-intro">Sample excerpts and their recorded revisions.</p>${scenario()
    .sources.map(
      ([title, version, excerpt]) =>
        `<article class="source-item">${icon("file")}<div><strong>${esc(title)}</strong><small>${esc(version)} · sample</small><p>${esc(excerpt)}</p></div></article>`,
    )
    .join("")}`;
}
function activityView() {
  const t = current(),
    s = scenario();
  const steps = [
    ["Request received", "Sample conversation · this session"],
    [`${s.sources.length} source records consulted`, "Recorded source revisions are available in Sources."],
    [
      s.readOnly ? "Answer prepared without changes" : `Proposal prepared · revision ${t.revision}`,
      s.readOnly ? "No approval required." : "Approval applies to one exact action.",
    ],
  ];
  if (t.approved) steps.push(["You approved the exact action", "Decision recorded · sample"]);
  if (["verifying", "done"].includes(t.scene) || t.records.length)
    steps.push(["Committed by the system", "Sample commit record"]);
  t.records.forEach(r => steps.push([`${r.action.title} checked`, `${r.action.recordId} · sample independent read-back`]));
  steps.push([
    s.readOnly ? "Read-only answer" : label(t),
    t.scene === "unknown" ? "Do not replay a possibly committed action." : "Current state in this example.",
  ]);
  return `<h2 class="view-heading">What happened</h2><p class="view-intro">Recorded steps, with your decisions kept in context.</p><ol class="activity-list">${steps.map(([a, b]) => `<li>${esc(a)}<small>${esc(b)}</small></li>`).join("")}</ol>`;
}
function footer() {
  const t = current(),
    s = scenario();
  if (s.readOnly)
    return '<div><strong>Read-only answer</strong>No changes made</div><button class="secondary" data-action="close-workspace">Back to chat</button>';
  if (t.scene === "unknown")
    return `<div><strong>Result unresolved</strong>No automatic resend</div><button class="secondary" data-action="reconcile">${icon("search")}${t.checked ? "Recovery details" : "Check result"}</button>`;
  if (t.scene === "stale" || t.scene === "rejected" || t.scene === "failed")
    return `<div><strong>${esc(label(t))}</strong>Approval unavailable for this revision</div><button class="secondary" data-action="refresh">${t.scene === "stale" ? "Prepare new review" : "Review proposal again"}</button>`;
  if (t.scene === "executing")
    return '<div><strong>Sending approved action</strong>Not complete, not verified</div><button class="stop-button" data-action="stop">' + icon("stop") + "Stop</button>";
  if (t.scene === "verifying")
    return '<div><strong>Committed · checking result</strong>Approval and commit are not verification</div><button class="stop-button" data-action="stop">' + icon("stop") + "Stop check</button>";
  if (t.scene === "done")
    return '<div><strong>Verified · sample</strong>Separate read-back evidence</div><button class="secondary" data-action="evidence">Inspect result</button>';
  return `<div><strong>${s.next ? `Action ${t.step + 1} of 2` : "One exact action"}</strong>This action has not been sent</div><div class="footer-actions"><button class="quiet-button" data-action="reject">Reject</button><button class="primary" data-action="approve">Review & approve</button></div>`;
}
function renderWorkspace() {
  if (current()) current().tab = tab;
  if (!current() || scenario().blocked) return;
  $("#workspace-title").textContent = action().title;
  $("#source-count").textContent = scenario().sources.length;
  $('.workspace-tabs [data-tab="document"]').textContent = scenario().readOnly
    ? "Answer"
    : current().step
      ? "Message"
      : "Document";
  document.querySelectorAll("[data-tab]").forEach(b => {
    const selected = b.dataset.tab === tab;
    b.setAttribute("aria-selected", String(selected));
    b.tabIndex = selected ? 0 : -1;
  });
  $("#workspace-body").setAttribute("aria-labelledby", `workspace-tab-${tab}`);
  $("#workspace-body").innerHTML =
    tab === "document" ? documentView() : tab === "sources" ? sourcesView() : activityView();
  $("#workspace-footer").innerHTML = footer();
  hydrate();
}

// ---- Study harness: prototype-only controls, outside the product surface (gap-audit F-6). ----
function studyActions() {
  const t = current();
  if (!t || scenario().blocked) return [];
  const restart = ["restart", "Restart this example"];
  switch (t.scene) {
    case "working":
      return [["finish-working", "Finish preparing (sample event)"], restart];
    case "review":
      return t.records.length ? [restart] : [["force-stale", "A source changes"], restart];
    case "executing":
      return [
        ["commit", "System confirms commit"],
        ["fail", "Execution fails"],
        ["lose-connection", "Connection lost · result unknown"],
        restart,
      ];
    case "verifying":
      return [["verify", "Read-back matches"], restart];
    default:
      return [restart];
  }
}
function renderStudy() {
  const panel = $("#study-panel");
  panel.hidden = !studyOpen;
  $("#study-toggle").setAttribute("aria-expanded", String(studyOpen));
  const items = studyActions();
  panel.innerHTML = `<p>Prototype controls that stand in for server events. They are not part of the product.</p>${
    items.length
      ? items.map(([id, text]) => `<button data-study="${id}">${esc(text)}</button>`).join("")
      : "<p>Open an example to see its controls.</p>"
  }`;
}

function dialog(title, body, actions = "") {
  previousFocus = document.activeElement;
  $("#dialog-content").innerHTML =
    `<div class="dialog-top"><h2 id="dialog-title" tabindex="-1">${esc(title)}</h2><button class="icon-button" data-action="close-dialog" aria-label="Close dialog">${icon("close")}</button></div>${body}${actions ? `<div class="dialog-actions">${actions}</div>` : ""}`;
  $("#dialog").showModal();
  $("#dialog-title").focus();
}
function closeDialog() {
  $("#dialog").close();
  if (previousFocus?.isConnected) previousFocus.focus();
}
function freshThread(id, prompt) {
  const s = scenarios[id];
  return {
    id: ++serial,
    scenario: id,
    prompt: prompt || s.prompt,
    draft: "",
    followups: [],
    context: [],
    scene: s.blocked ? "review" : "working",
    step: 0,
    revision: 1,
    clarification: "",
    records: [],
    checked: false,
  };
}
function start(id, prompt = "") {
  saveDraft();
  threads.unshift(freshThread(id, prompt));
  activeId = serial;
  workspaceOpen = false;
  tab = "document";
  if (isMobile()) setNav(false);
  render();
  announce(`${scenarios[id].short}: ${scenarios[id].blocked ? "access needed" : "working"}. Sample data.`);
  $("#prompt").focus();
}
function newChat() {
  saveDraft();
  activeId = null;
  workspaceOpen = false;
  if (isMobile()) setNav(false);
  render();
  $("#prompt").focus();
}
function showConnections() {
  dialog(
    "Your work context",
    `<p>These are fictional connections for this study. Availability does not represent a live access check.</p>${connections.map(([name, , scope, status]) => `<div class="connection-row">${icon("connections")}<div><strong>${esc(name)}</strong><small>${esc(scope)}<br>${esc(status)} · sample configuration, not probed</small></div></div>`).join("")}`,
  );
}
function approve() {
  if (current()?.scene !== "review" || scenario().readOnly || scenario().blocked) return;
  const a = action();
  dialog(
    "Approve this exact change?",
    `<p>This decision applies only to the action and content below.</p>${consequenceBlock()}${metadata(a)}${terms(a.fields)}<p>${esc(a.disclosure)}</p><div class="document-copy"><h2>${esc(a.body)}</h2><p>${esc(a.text)}</p></div>`,
    `<button class="secondary" data-action="close-dialog">Back to review</button><button class="primary" data-action="confirm">Approve this action</button>`,
  );
}
function update() {
  const wasInWorkspace = $("#workspace").contains(document.activeElement);
  render();
  announce(`${scenario().short}: ${label(current())}.`);
  if (wasInWorkspace && !$("#workspace").hidden) $("#workspace-body").focus();
  else if (wasInWorkspace) $("#prompt").focus();
}
function stop() {
  const t = current();
  if (!t || !stoppable.has(t.scene)) return;
  if (t.scene === "working" || t.scene === "needs-input") {
    t.scene = "stopped";
    t.stoppedNote = "";
  } else if (t.scene === "executing") {
    t.scene = "unknown";
    t.stoppedNote =
      "Stopped after the approved action was sent. It may already have completed, so I will not resend it.";
  } else {
    t.scene = "unknown";
    t.stoppedNote = "Stopped the result check. The action was committed, but its result is not verified.";
  }
  t.checked = false;
  update();
}
function study(id) {
  const t = current();
  if (!t) return;
  switch (id) {
    case "finish-working":
      if (scenario().next && !t.clarification) {
        t.scene = "needs-input";
        break;
      }
      t.scene = scenario().readOnly ? "done" : "review";
      if (!scenario().readOnly && !isMobile()) workspaceOpen = true;
      break;
    case "force-stale":
      t.scene = "stale";
      break;
    case "commit":
      t.scene = "verifying";
      break;
    case "fail":
      t.scene = "failed";
      break;
    case "lose-connection":
      t.scene = "unknown";
      t.stoppedNote = "";
      break;
    case "verify":
      t.records.push(sampleReadBack(t.approved));
      if (scenario().next && t.step === 0) {
        t.step = 1;
        t.scene = "review";
        t.approved = undefined;
      } else t.scene = "done";
      break;
    case "restart":
      Object.assign(t, freshThread(t.scenario, t.prompt), { id: t.id });
      serial--;
      workspaceOpen = false;
      break;
  }
  tab = "document";
  studyOpen = false;
  update();
  renderStudy();
}

document.addEventListener("click", e => {
  const b = e.target.closest("button,[data-action]");
  if (!b) return;
  if (b.id === "study-toggle") {
    studyOpen = !studyOpen;
    renderStudy();
    return;
  }
  if (b.dataset.study) {
    study(b.dataset.study);
    return;
  }
  if (b.dataset.audience) {
    const t = current();
    const wasPrepared = t.scene === "review";
    t.clarification = b.dataset.audience;
    if (wasPrepared) t.revision++;
    t.scene = "review";
    if ($("#dialog").open) closeDialog();
    if (!isMobile()) workspaceOpen = true;
    tab = "document";
    update();
    announce(`Audience set to ${b.dataset.audience}. ${wasPrepared ? "A new proposal revision is ready for review." : "Proposal ready for review."}`);
    return;
  }
  if (b.dataset.suggest) {
    $("#prompt").value = b.dataset.suggest;
    saveDraft();
    sizeComposer();
    $("#prompt").focus();
    return;
  }
  if (b.dataset.inspectSource !== undefined) {
    const [name, revision, excerpt] = scenario().sources[Number(b.dataset.inspectSource)];
    dialog(name, `<p>${esc(revision)} · sample source</p><blockquote>${esc(excerpt)}</blockquote>`);
    return;
  }
  if (b.dataset.addContext !== undefined) {
    const index = Number(b.dataset.addContext);
    if (!current().context.includes(index)) current().context.push(index);
    closeDialog();
    renderComposer();
    hydrate();
    $("#prompt").focus();
    return;
  }
  if (b.dataset.removeContext !== undefined) {
    current().context = current().context.filter(i => i !== Number(b.dataset.removeContext));
    renderComposer();
    hydrate();
    $("#prompt").focus();
    return;
  }
  if (b.dataset.start) {
    if ($("#dialog").open) closeDialog();
    start(b.dataset.start, pendingPrompt);
    pendingPrompt = "";
    return;
  }
  if (b.dataset.thread) {
    saveDraft();
    activeId = Number(b.dataset.thread);
    workspaceOpen = current().workspaceOpen ?? false;
    tab = current().tab || "document";
    if (isMobile()) setNav(false);
    render();
    (workspaceOpen && isMobile() ? $("#workspace .icon-button") : $("#prompt")).focus();
    return;
  }
  if (b.dataset.tab) {
    tab = b.dataset.tab;
    renderWorkspace();
    return;
  }
  const t = current();
  switch (b.dataset.action) {
    case "nav":
      setNav(!navOpen);
      break;
    case "history":
      setNav(true);
      break;
    case "new":
      newChat();
      break;
    case "add-context":
      addContext();
      break;
    case "connections":
      showConnections();
      break;
    case "workspace":
      setWorkspace(true);
      $("#workspace .icon-button").focus();
      break;
    case "close-workspace":
      setWorkspace(false);
      ($("#reopen").hidden ? $("#prompt") : $("#reopen")).focus();
      break;
    case "close-dialog":
      pendingPrompt = "";
      closeDialog();
      break;
    case "approve":
      approve();
      break;
    case "confirm":
      if (t.scene !== "review") break;
      t.approved = structuredClone(action());
      t.scene = "executing";
      closeDialog();
      update();
      break;
    case "stop":
      stop();
      break;
    case "audience":
      dialog(
        "Who should receive this?",
        `<p>Changing the audience prepares a new proposal revision. Nothing has been sent.</p><div class="choice-list">${audiences.map(([name, note]) => `<button data-audience="${esc(name)}" ${t.clarification === name ? "disabled" : ""}>${esc(name)}<small>${esc(note)} · sample${t.clarification === name ? " · current" : ""}</small></button>`).join("")}</div>`,
      );
      break;
    case "reject":
      t.scene = "rejected";
      update();
      break;
    case "refresh":
      if (t.scene === "stale" || t.scene === "failed") t.revision++;
      t.scene = "review";
      t.approved = undefined;
      tab = "document";
      update();
      break;
    case "restart":
      study("restart");
      break;
    case "reconcile":
      if (t.checked) {
        dialog(
          "An operator needs to investigate",
          "<p>The sample read-back is unresolved. Preserve the action reference and inspect the external record before another write. No resend was attempted.</p>",
        );
      } else {
        t.checked = true;
        update();
      }
      break;
    case "evidence":
      dialog(
        "Observed results · sample",
        `<p>Fictional read-back records, separate from input sources.</p>${t.records.map(r => `<article class="readback"><h3>${esc(r.action.title)}</h3>${terms([["Observed record", r.action.recordId], ["Verifier", r.verifier], ["Observation time", r.observedAt], ["Outcome", r.outcome], ["Destination", r.action.destination], ["Audience", r.action.scope], ...r.action.fields])}</article>`).join("")}`,
      );
      break;
  }
});
$("#composer").addEventListener("submit", e => {
  e.preventDefault();
  const text = $("#prompt").value.trim();
  if (!text) {
    $("#prompt").focus();
    return;
  }
  if (current()) {
    const t = current();
    t.followups.push({
      prompt: text,
      answer: answerFollowup(text, scenario(), t, scenario().blocked ? null : action()),
      context: [...t.context],
    });
    t.context = [];
    current().draft = "";
    render();
    $("#conversation-scroll").scrollTo({ top: $("#conversation-scroll").scrollHeight, behavior: "instant" });
    $("#prompt").focus();
  } else {
    pendingPrompt = text;
    dialog(
      "Choose an example to explore",
      `<p>This mockup does not call a model. Your message will be kept with the example you choose.</p><div class="choice-list">${Object.entries(
        scenarios,
      )
        .map(([id, s]) => `<button data-start="${id}">${esc(s.title)}<small>${esc(s.description)}</small></button>`)
        .join("")}</div>`,
    );
  }
});
$("#prompt").addEventListener("input", () => {
  saveDraft();
  sizeComposer();
});
$("#prompt").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
});
$("#dialog").addEventListener("cancel", () => {
  if (previousFocus?.isConnected) previousFocus.focus();
  pendingPrompt = "";
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && !$("#dialog").open && navOpen) {
    setNav(false);
    (isMobile() ? $(".mobile-nav") : $(".collapsed-toggle")).focus();
  }
});
applyTheme();
render();
window.addEventListener("resize", () => {
  $(".main").inert = navOpen && isMobile();
  if (navOpen && isMobile() && $(".main").contains(document.activeElement)) {
    $(".expanded-toggle").focus();
  } else if (workspaceOpen && isMobile() && $(".conversation").contains(document.activeElement)) {
    $("#workspace .icon-button").focus();
  }
});
bindTabKeys($(".workspace-tabs"), button => button.click());
