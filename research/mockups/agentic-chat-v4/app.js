import { MOBILE_QUERY } from "./design-system/generated/metrics.js";
const isMobile = () => matchMedia(MOBILE_QUERY).matches;
import { composerMarkup, statusMarkup, bindTabKeys } from "./design-system/components.js";
import { followupQuestions, highlights, answerFollowup } from "./chat-content.js";
import { icon, logo } from "./design-system/icons.js";
import { scenarios, connections } from "../agentic-workspace-v3/fixtures.js";
import { actionView, sampleReadBack } from "../agentic-workspace-v3/action-model.js";
const $ = s => document.querySelector(s);
$("#composer-slot").outerHTML = composerMarkup();
const esc = value =>
  String(value ?? "").replace(
    /[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const theme = new URLSearchParams(location.search).get("theme");
if (["light", "dark", "high-contrast"].includes(theme)) document.documentElement.dataset.theme = theme;
const threads = [];
let activeId = null,
  navOpen = false,
  workspaceOpen = false,
  tab = "document",
  serial = 0,
  pendingPrompt = "",
  emptyDraft = "",
  previousFocus;
const current = () => threads.find(t => t.id === activeId);
const scenario = () => scenarios[current()?.scenario];
const action = () => actionView(scenario(), current());
const label = t =>
  ({
    review: "Needs review",
    verifying: "Checking result",
    done: "Verified",
    unknown: "Outcome unknown",
    stale: "Review outdated",
    rejected: "Not approved",
  })[t.scene];
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
function renderHistory() {
  $("#history").innerHTML = threads
    .map(
      t =>
        `<button data-thread="${t.id}" class="${t.id === activeId ? "selected" : ""}">${esc(scenarios[t.scenario].short)}<small>${scenarios[t.scenario].readOnly ? "Read-only answer" : scenarios[t.scenario].blocked ? "Needs access" : label(t)}</small></button>`,
    )
    .join("");
  $("#empty-history").hidden = threads.length > 0;
}
function setWorkspace(open) {
  workspaceOpen = open && !!current() && !scenario().blocked;
  $("#workspace").hidden = !workspaceOpen;
  $("#surface").classList.toggle("has-workspace", workspaceOpen);
  $("#reopen").hidden = !current() || scenario().blocked || workspaceOpen;
  if (current()) current().workspaceOpen = workspaceOpen;
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
  setWorkspace(workspaceOpen);
  hydrate();
}
function welcome() {
  return `<div class="welcome"><div class="welcome-mark">${logo()}</div><h1>What shall we<br>move forward?</h1><p>Bring a question. Untangle a problem.<br>Turn a conversation into work, together.</p><div class="starters"><button data-start="handoff">${icon("file")}Prepare a handoff</button><button data-start="knowledge">${icon("search")}Find an answer</button><button data-start="procurement">${icon("purchase")}Draft an order</button></div></div>`;
}
function artifactLink() {
  const t = current(),
    s = scenario();
  return `<button class="artifact-link" data-action="workspace">${icon(t.step ? "chat" : s.readOnly ? "book" : "file")}<span><strong>${esc(action().title)}</strong><small>${s.readOnly ? "Read-only · 2 sources" : label(t) + " · " + (t.step ? "Action 2 of 2" : s.next ? "Action 1 of 2" : "One action")} · Open workspace</small></span>${icon("arrow")}</button>`;
}
function conversation() {
  const t = current(),
    s = scenario();
  let reply;
  if (s.blocked)
    reply =
      '<p>I need access to the people directory before I can prepare a plan for this teammate. No employee records have been read.</p><button class="secondary" data-action="connections">View connections</button>';
  else if (s.readOnly)
    reply = `<p>${esc(s.intro)}</p><p>The regional limit depends on the employee’s region, which is not included here. Check that before making a booking.</p>${artifactLink()}`;
  else if (t.scene === "unknown")
    reply = `<p>The request was sent, but its result is still unknown. It may have completed.</p><div class="inline-notice">${t.checked ? "The sample check is still unresolved. An operator needs to investigate." : "I won’t resend it. Check the existing action before deciding what happens next."}</div>${artifactLink()}`;
  else if (t.scene === "stale")
    reply = `<p>A source changed after the draft was prepared. This revision can no longer be approved.</p>${artifactLink()}`;
  else if (t.scene === "rejected")
    reply = `<p>You rejected this proposal. No action was sent for this revision. Earlier completed actions remain unchanged.</p>${artifactLink()}`;
  else if (t.scene === "verifying")
    reply = `<p>The action was approved. The next step is an independent check of its result.</p>${artifactLink()}`;
  else if (t.scene === "done")
    reply = `<p>${s.next ? "The document and message have separate sample read-back records." : "The sample result matches the approved action."}</p>${artifactLink()}`;
  else
    reply = `<details class="source-trace"><summary>${icon("check")}Checked ${s.sources.length} sample sources ${icon("chevron")}</summary><div>${sourceLinks()}</div></details><p>${t.step ? "The document has been created and checked in this example. The message is a separate action for you to review." : esc(s.intro)}</p>${chatHighlights()}${artifactLink()}<p class="view-intro">${t.step ? "Only this message is awaiting approval." : s.next ? "I’ll create the document first. Sharing the message will need a separate approval." : "Review the proposed change in the workspace before approving."}</p>`;
  return `<article class="message user">${esc(t.prompt)}</article><article class="message assistant"><div class="author">${logo()}e-agent <span>Sample response</span></div>${reply}</article>${t.followups.map(f => `<article class="message user">${esc(f.prompt)}${f.context.length ? `<div class="sent-context">${f.context.map(i => `${icon("file")} ${esc(s.sources[i][0])}`).join(" · ")}</div>` : ""}</article><article class="message assistant"><div class="author">${logo()}e-agent <span>Sample response</span></div><p>${esc(f.answer)}</p>${f.prompt === followupQuestions[0] && !s.blocked ? `<div class="source-links">${sourceLinks()}</div>` : ""}</article>`).join("")}<div class="followup-suggestions" aria-label="Suggested follow-ups"><span>Continue the conversation</span>${followupQuestions
    .slice(0, 2)
    .map(q => `<button data-suggest="${esc(q)}">${esc(q)} ${icon("arrow")}</button>`)
    .join("")}</div>`;
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
function documentView() {
  const t = current(),
    s = scenario(),
    a = action();
  return `<article class="document"><div class="document-label"><span class="overline">${s.readOnly ? "KNOWLEDGE" : t.step ? "MESSAGE" : s.category.toUpperCase()} / ${s.readOnly ? "REFERENCE" : `REVISION ${t.revision}`}</span>${statusMarkup(s.readOnly ? "neutral" : { review: "attention", verifying: "progress", done: "verified", unknown: "unknown", stale: "attention", rejected: "cancelled" }[t.scene], s.readOnly ? "Read-only" : t.scene === "unknown" ? "Sent · unresolved" : label(t))}</div><h1>${esc(a.title)}</h1><p class="lede">${esc(t.step ? "A separate message for your review." : s.summary)}</p>${!s.readOnly ? `<div class="scope">${icon("shield")}<div><strong>${esc(a.destination)}</strong><br>${esc(a.scope)} · this action only</div></div>` : ""}${terms(a.fields)}<div class="document-copy"><h2>${esc(a.body)}</h2><p>${esc(a.text)}</p></div><details class="audit"><summary>${s.readOnly ? "Reference details" : "Exact action & access details"}</summary>${metadata(a)}<p>${esc(a.disclosure)}</p><p>Source revisions: ${a.sources.map(esc).join("; ")}</p></details></article>`;
}
function sourcesView() {
  return `<h2 class="view-heading">Sources behind the work</h2><p class="view-intro">Sample excerpts and their recorded revisions.</p>${scenario()
    .sources.map(
      ([title, version, excerpt]) =>
        `<article class="source-item">${icon("file")}<div><strong>${esc(title)}</strong><small>${esc(version)}</small><p>${esc(excerpt)}</p></div></article>`,
    )
    .join("")}`;
}
function activityView() {
  const t = current(),
    s = scenario();
  return `<h2 class="view-heading">What happened</h2><p class="view-intro">Observable steps, with your decisions kept in context.</p><ol class="activity-list"><li>Request received<small>Sample conversation · this session</small></li><li>${s.sources.length} source records consulted<small>Recorded source revisions are available in Sources.</small></li><li>${s.readOnly ? "Answer prepared without changes" : "Proposal prepared · revision " + t.revision}<small>${s.readOnly ? "No approval required." : "Approval applies to one exact action."}</small></li>${t.records.map(r => `<li>${esc(r.action.title)} checked<small>${esc(r.action.recordId)} · sample independent read-back</small></li>`).join("")}<li>${s.readOnly ? "Read-only answer" : label(t)}<small>${t.scene === "unknown" ? "Do not replay a possibly committed action." : "Current state in this example."}</small></li></ol>${!s.readOnly ? `<details class="simulation"><summary>Explore prototype states</summary><div><button data-action="restart">Restart example</button>${t.scene === "review" && !t.records.length ? '<button data-scene="stale">Changed source</button><button data-scene="unknown">Unknown result</button>' : ""}${s.next && t.scene === "review" ? '<button data-action="audience">Change audience</button>' : ""}</div></details>` : ""}`;
}
function footer() {
  const t = current(),
    s = scenario();
  if (s.readOnly)
    return '<div><strong>Read-only answer</strong>No changes made</div><button class="secondary" data-action="close-workspace">Back to chat</button>';
  if (t.scene === "unknown")
    return `<div><strong>Result unresolved</strong>No automatic resend</div><button class="secondary" data-action="reconcile">${icon("search")}${t.checked ? "Recovery details" : "Check result"}</button>`;
  if (t.scene === "stale" || t.scene === "rejected")
    return `<div><strong>${label(t)}</strong>Approval unavailable</div><button class="secondary" data-action="refresh">${t.scene === "rejected" ? "Review proposal again" : "Prepare new review"}</button>`;
  if (t.scene === "verifying")
    return '<div><strong>Checking the outcome</strong>Approval is not verification</div><button class="secondary" data-action="verify">Simulate read-back</button>';
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
function start(id, prompt = "") {
  saveDraft();
  const s = scenarios[id];
  threads.unshift({
    id: ++serial,
    scenario: id,
    prompt: prompt || s.prompt,
    draft: "",
    followups: [],
    context: [],
    scene: s.readOnly ? "done" : "review",
    step: 0,
    revision: 1,
    clarification: "",
    records: [],
    checked: false,
  });
  activeId = serial;
  workspaceOpen = !s.readOnly && !s.blocked;
  tab = "document";
  if (isMobile()) {
    workspaceOpen = false;
    setNav(false);
  }
  render();
  announce(s.short + " prepared from fictional data.");
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
    `<p>This decision applies only to the action and content below.</p>${metadata(a)}${terms(a.fields)}<p>${esc(a.disclosure)}</p><div class="document-copy"><h2>${esc(a.body)}</h2><p>${esc(a.text)}</p></div>`,
    `<button class="secondary" data-action="close-dialog">Back to review</button><button class="primary" data-action="confirm">Approve this action</button>`,
  );
}
function update() {
  const wasInWorkspace = $("#workspace").contains(document.activeElement);
  render();
  announce(`${scenario().short}: ${label(current())}.`);
  if (wasInWorkspace) {
    $("#workspace-body").focus();
  }
}
document.addEventListener("click", e => {
  const b = e.target.closest("button,[data-action]");
  if (!b) return;
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
  if (b.dataset.scene) {
    if (current().scene !== "review" || current().records.length) return;
    current().scene = b.dataset.scene;
    current().checked = false;
    tab = "document";
    update();
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
      $("#reopen").focus();
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
      t.scene = "verifying";
      closeDialog();
      update();
      break;
    case "verify":
      if (t.scene !== "verifying") break;
      t.records.push(sampleReadBack(t.approved));
      if (scenario().next && t.step === 0) {
        t.step = 1;
        t.scene = "review";
      } else t.scene = "done";
      tab = "document";
      update();
      break;
    case "reject":
      t.scene = "rejected";
      update();
      break;
    case "refresh":
      if (t.scene === "stale") t.revision++;
      t.scene = "review";
      tab = "document";
      update();
      break;
    case "restart":
      Object.assign(t, {
        step: 0,
        revision: 1,
        scene: "review",
        records: [],
        checked: false,
        clarification: "",
        approved: undefined,
      });
      tab = "document";
      update();
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
    case "audience":
      dialog(
        "Who should receive this?",
        `<p>Changing the audience prepares a new proposal revision. ${t.step ? "The created document keeps its approved access; only this message changes." : ""}</p><div class="choice-list">${!t.step || t.records[0]?.action.scope !== "Project owner only" ? '<button data-audience="Delivery team only">Delivery team only<small>8 internal members</small></button>' : ""}<button data-audience="Project owner only">Project owner only<small>Alex Morgan · direct message</small></button></div>`,
      );
      break;
  }
  if (b.dataset.audience) {
    t.clarification = b.dataset.audience;
    t.revision++;
    t.scene = "review";
    closeDialog();
    tab = "document";
    update();
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
    $("#conversation-scroll").scrollTo({
      top: $("#conversation-scroll").scrollHeight,
      behavior: "instant",
    });
    $("#prompt").focus();
  } else {
    pendingPrompt = text;
    dialog(
      "Choose an example to explore",
      `<p>This mockup does not call a model. Your message will be kept with the example you choose.</p><div class="choice-list">${Object.entries(
        scenarios,
      )
        .map(
          ([id, s]) =>
            `<button data-start="${id}">${esc(s.title)}<small>${esc(s.description)}</small></button>`,
        )
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
