// Conversation thread mockup (Phase 4, Task 4e.2). Research artifact, not product code.
// It renders fixed sample states from scenario.js. Nothing calls a model, a server or a network.
// All content is built with textContent, so sample text is inert (AG-ID-2).
import { STRINGS } from "./strings.js";
import { VARIANTS, STATES, TEXT, EXAMPLES, APPROVAL, CITATIONS, SOURCES, EVENTS, VERIFIED_VALUES, GALLERY } from "./scenario.js";

const params = new URLSearchParams(location.search);
const pick = (key, allowed, fallback) => (allowed.includes(params.get(key)) ? params.get(key) : fallback);
const STATE_IDS = STATES.map(s => s.id);
// Internal states reached only by acting inside a sample (approve, reject, stop).
const INTERNAL = ["approved", "rejected", "stopped"];

const S = {
  variant: pick("variant", VARIANTS.map(v => v.id), "a1"),
  state: pick("state", [...STATE_IDS, ...INTERNAL], "empty"),
  lang: pick("lang", ["en", "vi"], "en"),
  theme: pick("theme", ["light", "dark", "high-contrast"], "light"),
  surface: pick("surface", ["page", "docked"], "page"),
  mode: pick("mode", ["off", "shadow", "features", "route-error"], "off"),
  ws: { open: false, run: null, tab: null, opener: null },
  draft: "",
  refusal: null,
  confirm: false,
  navOpen: false,
  explainOpen: false,
  showMsgs: {},
  protoNote: null,
  stoppedFrom: null,
};

const t = key => STRINGS[S.lang][key] ?? STRINGS.en[key] ?? key;
const L = v => (v && typeof v === "object" && "en" in v ? v[S.lang] : v);
const MARKER = { neutral: "·", progress: "◍", attention: "◆", verified: "✓", failed: "✕", unknown: "？" };

// h(tag, attrs, ...children): DOM builder. Strings become text nodes; nothing is parsed as HTML.
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const badge = (tone, label, extra = {}) =>
  h("span", { class: `badge badge-${tone}`, "data-tone": tone, ...extra }, h("span", { class: "badge-marker", "aria-hidden": "true" }, MARKER[tone]), label);
const sampleTag = () => h("span", { class: "sample-tag" }, t("sample"));
const btn = (label, attrs = {}) => h("button", { type: "button", class: "btn", ...attrs }, label);

// ---------- Thread model per sample state ----------
const ev = (run, n) => EVENTS[run].slice(0, n);
const extraEv = (time, en, vi) => [time, { en, vi }];
const msgUser = text => ({ who: "user", text });
const msgReply = text => ({ who: "agent", text, label: "conversation.reply" });
const msgQuestion = text => ({ who: "agent", text, label: "messages.question" });
const msgFinal = text => ({ who: "agent", text, label: "messages.agentWords", final: true });

const R1_REPLY = () => ({
  n: 1, title: TEXT.u_hi, statusKey: "status.WAITING_INPUT.reply", tone: "attention", active: true,
  msgs: [msgUser(TEXT.u_hi), msgReply(TEXT.a_reply)], line: null,
  tabs: ["sources", "activity"], events: ev(1, 2), sources: [], carried: [],
});
const R1_GROUNDED = () => ({
  n: 1, title: TEXT.u_hi, statusKey: "status.SUCCEEDED.grounded", tone: "neutral", active: false,
  msgs: [msgUser(TEXT.u_hi), msgReply(TEXT.a_reply), msgUser(TEXT.u_short), msgFinal(TEXT.a_grounded)],
  line: TEXT.r1_line, result: "grounded", tabs: ["result", "sources", "activity"], events: ev(1, 7), sources: SOURCES[1], carried: [],
});
const R2 = over => ({
  n: 2, title: TEXT.u_po, carried: [1], msgs: [msgUser(TEXT.u_po), msgQuestion(TEXT.a_question), msgUser(TEXT.u_40)], ...over,
});

function model(state) {
  switch (state) {
    case "empty":
      return { runs: [], composer: "new" };
    case "reply":
      return { runs: [R1_REPLY()], composer: "answer", answering: 1 };
    case "grounded":
      return { runs: [R1_GROUNDED()], composer: "new", auto: { run: 1, tab: "result" } };
    case "clarification":
      return {
        runs: [R1_GROUNDED(), R2({ statusKey: "status.WAITING_INPUT", tone: "attention", active: true, msgs: [msgUser(TEXT.u_po), msgQuestion(TEXT.a_question)], tabs: ["sources", "activity"], events: ev(2, 4), sources: SOURCES[2].slice(0, 1), line: null })],
        composer: "answer", answering: 2, answerKind: "question",
      };
    case "running":
      return { runs: [R1_GROUNDED(), R2({ statusKey: "status.RUNNING", tone: "progress", active: true, line: null, tabs: ["sources", "activity"], events: ev(2, 6), sources: SOURCES[2].slice(0, 2) })], composer: "busy", next: "approval" };
    case "approval":
    case "refused":
      return { runs: [R1_GROUNDED(), R2({ statusKey: "status.WAITING_APPROVAL", tone: "attention", active: true, line: TEXT.r2_waiting, decision: "pending", tabs: ["decision", "sources", "activity"], events: ev(2, 8), sources: SOURCES[2] })], composer: "busy", auto: { run: 2, tab: "decision" } };
    case "approved":
      return { runs: [R1_GROUNDED(), R2({ statusKey: "status.VERIFYING", tone: "progress", active: true, line: TEXT.r2_waiting, decision: "approved", committed: true, tabs: ["decision", "sources", "activity"], events: ev(2, 11), sources: SOURCES[2] })], composer: "busy", next: "verified" };
    case "rejected":
      return { runs: [R1_GROUNDED(), R2({ statusKey: "status.REJECTED", tone: "neutral", active: false, line: TEXT.r2_waiting, decision: "rejected", tabs: ["decision", "sources", "activity"], events: [...ev(2, 8), extraEv("09:47", "Rejected by you · nothing written", "Bạn đã từ chối · không ghi dữ liệu")], sources: SOURCES[2] })], composer: "new" };
    case "verified":
      return { runs: [R1_GROUNDED(), R2({ statusKey: "status.SUCCEEDED", tone: "verified", active: false, msgs: [msgUser(TEXT.u_po), msgQuestion(TEXT.a_question), msgUser(TEXT.u_40), msgFinal(TEXT.a_verified)], line: TEXT.r2_verified, decision: "approved", result: "verified", tabs: ["result", "decision", "sources", "activity"], events: ev(2, 13), sources: SOURCES[2] })], composer: "new", auto: { run: 2, tab: "result" } };
    case "failed":
      return { runs: [R1_GROUNDED(), R2({ statusKey: "status.FAILED", tone: "failed", active: false, line: TEXT.r2_failed, result: "failed", tabs: ["result", "sources", "activity"], events: [...ev(2, 6), extraEv("09:45", "Could not read purchase rules · time limit reached", "Không đọc được quy tắc mua hàng · hết thời hạn"), extraEv("09:45", "Task stopped · nothing written", "Yêu cầu đã dừng · không ghi dữ liệu")], sources: SOURCES[2].slice(0, 2) })], composer: "new", auto: { run: 2, tab: "result" } };
    case "ended-answer":
      return { runs: [R1_GROUNDED(), R2({ statusKey: "status.CANCELLED", tone: "neutral", active: false, msgs: [msgUser(TEXT.u_po), msgQuestion(TEXT.a_question)], line: TEXT.r2_cancelled, tabs: ["sources", "activity"], events: [...ev(2, 4), extraEv("09:46", "Stopped by you · nothing sent", "Bạn đã dừng · chưa gửi gì")], sources: SOURCES[2].slice(0, 1) })], composer: "new" };
    case "stopped": {
      const from = model(S.stoppedFrom || "running");
      const last = from.runs[from.runs.length - 1];
      const line = last.committed
        ? { en: "Stopped. The draft order was recorded but not verified; open the result to check it.", vi: "Đã dừng. Đơn nháp đã được ghi nhưng chưa xác minh; hãy mở kết quả để kiểm tra." }
        : { en: t("run.stopped"), vi: STRINGS.vi["run.stopped"] };
      from.runs[from.runs.length - 1] = { ...last, statusKey: "status.CANCELLED", tone: "neutral", active: false, line, decision: last.decision === "pending" ? null : last.decision, tabs: last.tabs.filter(x => x !== "decision" || last.decision !== "pending"), events: [...last.events, extraEv("09:46", "Stopped by you", "Bạn đã dừng")] };
      return { runs: from.runs, composer: "new" };
    }
    case "gallery":
      return { runs: [], composer: "new", gallery: true };
    default:
      return { runs: [], composer: "new" };
  }
}

// Refusals preset by a sample state (the server's 409 envelope: fixed hint + correlation id).
const PRESET_REFUSAL = {
  refused: { kind: "busy", server: "wait, decide the approval, or stop the run", draft: TEXT.u_busy },
  "ended-answer": { kind: "question", server: "the question changed; read it again", draft: TEXT.u_40 },
};
// What sending does in each sample: the server's route (ADR 0023 §4), then the next sample.
const SEND = {
  empty: { go: "reply" },
  reply: { go: "grounded" },
  grounded: { go: "clarification" },
  clarification: { go: "running" },
  running: { refuse: "busy" },
  approval: { refuse: "busy" },
  refused: { refuse: "busy" },
  approved: { refuse: "busy" },
};

// ---------- Entering a state ----------
function wide() {
  const app = document.getElementById("app");
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  return app && app.clientWidth >= 60 * rem;
}
function enter(state, { keepDraft = false } = {}) {
  S.state = state;
  S.confirm = false;
  S.explainOpen = false;
  S.protoNote = null;
  const preset = PRESET_REFUSAL[state];
  S.refusal = preset ? { kind: preset.kind, server: preset.server, ref: "corr-sample-7f3c91a2" } : null;
  if (preset) S.draft = L(preset.draft);
  else if (!keepDraft) S.draft = state === "fallback" && S.mode === "route-error" ? L(TEXT.u_fallbackDraft) : "";
  S.navOpen = state === "legacy";
  const m = model(state);
  document.body.dataset.surface = S.surface; // so wide() measures the real placement
  S.ws = { open: false, run: null, tab: null, opener: null };
  if (m.auto && wide()) S.ws = { open: true, run: m.auto.run, tab: m.auto.tab, opener: `open-${m.auto.run}` };
  syncUrl();
  render({ scrollEnd: m.runs.length > 0 });
  const last = m.runs[m.runs.length - 1];
  announce(last ? `${t("run")} ${last.n}: ${t(last.statusKey)}` : STATES.find(s => s.id === state)?.label[S.lang] || "");
}
function syncUrl() {
  const p = new URLSearchParams({ variant: S.variant, state: S.state, lang: S.lang, theme: S.theme, surface: S.surface });
  if (S.state === "fallback") p.set("mode", S.mode);
  history.replaceState(null, "", `?${p}`);
}
function announce(text) {
  const live = document.getElementById("announcer");
  live.textContent = "";
  requestAnimationFrame(() => (live.textContent = text));
}

// ---------- Actions ----------
function openWorkspace(run, tab, openerKey) {
  const m = model(S.state);
  const r = m.runs.find(x => x.n === run);
  if (!r) return;
  S.ws = { open: true, run, tab: tab && r.tabs.includes(tab) ? tab : r.tabs[0], opener: openerKey };
  S.confirm = false;
  render({ focus: "ws-heading" });
}
function closeWorkspace() {
  const opener = S.ws.opener;
  S.ws = { ...S.ws, open: false };
  S.confirm = false;
  render({ focus: opener || "prompt" });
}
function send() {
  const text = S.draft.trim();
  if (!text) return;
  const rule = SEND[S.state];
  if (rule?.refuse) {
    // The server refuses (409); the draft stays and the approval card is untouched (ADR 0034 §2).
    S.refusal = { kind: rule.refuse, server: rule.refuse === "busy" ? "wait, decide the approval, or stop the run" : "the question changed; read it again", ref: "corr-sample-7f3c91a2" };
    render({ focus: "prompt" });
    return;
  }
  if (rule?.go) {
    enter(rule.go);
    render({ focus: "prompt", scrollEnd: true });
    return;
  }
  S.protoNote = { en: "Prototype: this message would start a new run. Further runs are not modelled; your text is kept.", vi: "Nguyên mẫu: tin nhắn này sẽ bắt đầu một lượt mới. Các lượt tiếp theo không được mô phỏng; nội dung vẫn được giữ." };
  S.refusal = null;
  render({ focus: "prompt" });
}
function stop() {
  S.stoppedFrom = S.state;
  enter("stopped", { keepDraft: true });
  render({ focus: "prompt", scrollEnd: true });
}

// ---------- Rendering ----------
let lastFocusKey = null;
function render({ focus, scrollEnd = false } = {}) {
  const prevScroll = document.querySelector(".thread-scroll")?.scrollTop ?? 0;
  const active = document.activeElement;
  const prevKey = active?.dataset?.key || null;
  document.documentElement.lang = S.lang;
  document.documentElement.dataset.theme = S.theme;
  document.body.dataset.variant = S.variant;
  document.body.dataset.surface = S.surface;
  document.title = `e-agent · ${STATES.find(s => s.id === S.state)?.label[S.lang] || S.state} · ${S.variant.toUpperCase()} (mockup)`;
  renderProto();
  syncNext(); // before layout, so the scroll position below accounts for the prototype bar
  const app = document.getElementById("app");
  app.replaceChildren(renderApp());
  const scroller = app.querySelector(".thread-col .thread-scroll");
  if (scroller) scroller.scrollTop = scrollEnd ? scroller.scrollHeight : prevScroll;
  const key = focus || prevKey || lastFocusKey;
  if (key) {
    const el = app.querySelector(`[data-key="${CSS.escape(key)}"]`) || document.querySelector(`[data-key="${CSS.escape(key)}"]`);
    if (el && (focus || prevKey)) el.focus({ preventScroll: !focus });
  }
  lastFocusKey = null;
}

function renderProto() {
  const bar = document.getElementById("proto");
  const open = bar.querySelector("details")?.open ?? false;
  const stateLabel = STATES.find(s => s.id === S.state)?.label[S.lang] || S.state;
  const select = (id, label, options, value, onChange) =>
    h("label", { class: "proto-field" }, h("span", {}, label),
      h("select", { id, "data-key": id, onchange: e => onChange(e.target.value) },
        options.map(([v, l]) => h("option", { value: v, selected: v === value }, l))));
  const details = h("details", { class: "proto-details", open },
    h("summary", {}, h("span", { class: "proto-kicker" }, t("proto.title")), h("span", { class: "proto-current", "data-testid": "proto-current" }, `${S.variant.toUpperCase()} · ${stateLabel} · ${S.lang.toUpperCase()}`)),
    h("div", { class: "proto-fields" },
      select("proto-variant", t("proto.variant"), VARIANTS.map(v => [v.id, v.name[S.lang]]), S.variant, v => { S.variant = v; enter(S.state, { keepDraft: true }); }),
      select("proto-state", t("proto.state"), STATES.map(s => [s.id, s.label[S.lang]]).concat(INTERNAL.includes(S.state) ? [[S.state, S.state]] : []), S.state, v => enter(v)),
      select("proto-lang", t("proto.lang"), [["en", "English"], ["vi", "Tiếng Việt"]], S.lang, v => { S.lang = v; enter(S.state); }),
      select("proto-theme", t("proto.theme"), [["light", "Light"], ["dark", "Dark"], ["high-contrast", "High contrast"]], S.theme, v => { S.theme = v; syncUrl(); render(); }),
      select("proto-surface", t("proto.surface"), [["page", "Workspace (full page)"], ["docked", "Docked (embedded panel)"]], S.surface, v => { S.surface = v; enter(S.state, { keepDraft: true }); }),
      S.state === "fallback" ? select("proto-mode", t("proto.mode"), [["off", "off"], ["shadow", "shadow"], ["features", "features read failed"], ["route-error", "shadow · route error"]], S.mode, v => { S.mode = v; enter("fallback"); }) : null,
    ),
    h("p", { class: "proto-variant-summary" }, VARIANTS.find(v => v.id === S.variant).summary[S.lang]),
    h("p", { class: "proto-hint" }, S.lang === "vi"
      ? "Gửi tin nhắn chuyển sang trạng thái mẫu tiếp theo; luồng hiện tin nhắn đã ghi của mẫu, không phải nội dung bạn gõ."
      : "Sending moves to the next sample state; the thread shows the sample's recorded messages, not your text."),
  );
  bar.replaceChildren(details);
}

function renderApp() {
  if (S.state === "fallback") return renderFallback();
  const m = model(S.state);
  const shell = h("div", { class: `shell${S.ws.open ? " ws-open" : ""}${S.navOpen ? " nav-open" : ""}`, "data-state-sample": S.state });
  shell.append(renderHeader(), renderSidebar(), renderThreadColumn(m), renderWorkspace(m));
  return shell;
}

function renderHeader(title = S.state === "empty" ? { en: t("nav.new"), vi: STRINGS.vi["nav.new"] } : S.state === "legacy" ? TEXT.legacyRuns[0].title : TEXT.convTitle, { nav = true } = {}) {
  return h("header", { class: "app-header" },
    !nav ? null : h("button", { type: "button", class: "btn btn-quiet nav-toggle", "data-key": "nav-toggle", "aria-expanded": String(S.navOpen), "aria-controls": "sidebar", onclick: () => { S.navOpen = !S.navOpen; render({ focus: S.navOpen ? "nav-first" : "nav-toggle" }); } },
      h("span", { class: "icon-lines", "aria-hidden": "true" }), h("span", { class: "nav-toggle-label" }, t("nav.open"))),
    h("img", { class: "brand-mark", src: "../../../ui/packages/components/src/primitives/brand/e-agent-mark.svg", alt: "", width: 28, height: 28 }),
    h("div", { class: "app-title" }, h("span", { class: "product" }, "e-agent"), h("span", { class: "conv-title" }, L(title))),
    h("span", { class: "sample-badge", title: t("sample.note") }, t("sample")),
  );
}

function renderSidebar() {
  const nav = h("nav", { id: "sidebar", class: "sidebar", "aria-label": t("nav.conversations") });
  nav.append(
    h("div", { class: "sidebar-head" },
      h("button", { type: "button", class: "btn btn-primary", "data-key": "nav-first", onclick: () => enter("empty") }, t("nav.new")),
      h("button", { type: "button", class: "btn btn-quiet nav-close", "aria-label": t("nav.close"), "data-key": "nav-close", onclick: () => { S.navOpen = false; render({ focus: "nav-toggle" }); } }, "✕")),
    h("h2", { class: "nav-heading" }, t("nav.conversations")),
    h("ul", { class: "nav-list" }, TEXT.conversations.map(c => {
      const cur = c.current && S.state !== "legacy" ? currentConversation() : null;
      return h("li", {}, h("a", { href: "#", class: `nav-item${cur ? " current" : ""}`, "aria-current": cur ? "page" : null, onclick: e => e.preventDefault() },
        h("span", { class: "nav-title" }, L(c.title)),
        h("span", { class: "nav-meta" }, cur ? (cur.statusKey ? badge(cur.tone, t(cur.statusKey)) : h("span", { class: "last-seen" }, S.lang === "vi" ? "chưa có lượt nào" : "no runs yet")) : badge(c.tone, t(c.status)))));
    })),
    h("h2", { class: "nav-heading", id: "legacy-heading" }, t("nav.legacy")),
    h("p", { class: "nav-note" }, t("nav.legacyNote")),
    h("ul", { class: "nav-list legacy", "aria-labelledby": "legacy-heading", "data-testid": "legacy-group" }, TEXT.legacyRuns.map((r, i) =>
      h("li", {}, h("a", { href: "#", class: `nav-item${S.state === "legacy" && i === 0 ? " current" : ""}`, onclick: e => { e.preventDefault(); enter("legacy"); S.navOpen = false; render({ focus: "legacy-heading-main" }); } },
        h("span", { class: "nav-title" }, L(r.title)),
        h("span", { class: "nav-meta" }, h("span", { class: "last-seen" }, `${t("nav.lastSeen")} ·`), badge(r.tone, t(r.last))))))),
  );
  return nav;
}

// The current conversation's sidebar row shows its latest run, as GET /v1/conversations would.
function currentConversation() {
  const runs = model(S.state).runs;
  const last = runs[runs.length - 1];
  return last ? { statusKey: last.statusKey, tone: last.tone } : {};
}

function renderThreadColumn(m) {
  const col = h("main", { class: "thread-col", "aria-label": t("messages.title") });
  if (S.state === "legacy") {
    col.append(renderLegacyMain(), renderComposer({ runs: [], composer: "new" }));
    return col;
  }
  // A3: when the workspace is closed, a reopen bar keeps the latest run's status in view.
  const last = m.runs[m.runs.length - 1];
  if (S.variant === "a3" && !S.ws.open && last) {
    col.append(h("div", { class: "reopen-bar", "data-testid": "reopen-bar" },
      h("span", { class: "reopen-label" }, t("ws.closed")),
      h("span", {}, `${t("run")} ${last.n}`), badge(last.tone, t(last.statusKey)),
      h("button", { type: "button", class: "btn", "data-key": "reopen", onclick: () => openWorkspace(last.n, null, "reopen") }, t("ws.reopen"))));
  }
  const scroller = h("div", { class: "thread-scroll" });
  if (m.gallery) scroller.append(renderGallery());
  else if (!m.runs.length) scroller.append(renderEmpty());
  else {
    const list = h("ol", { class: "thread", "aria-label": t("messages.title") });
    m.runs.forEach((r, i) => list.append(renderRun(r, i === m.runs.length - 1, m)));
    scroller.append(list);
  }
  col.append(scroller, renderComposer(m));
  return col;
}

function renderEmpty() {
  return h("section", { class: "empty", "aria-labelledby": "empty-h" },
    h("img", { class: "empty-mark", src: "../../../ui/packages/components/src/primitives/brand/e-agent-mark.svg", alt: "", width: 56, height: 56 }),
    h("p", { class: "kicker" }, t("empty.kicker")),
    h("h1", { id: "empty-h" }, t("empty.heading")),
    h("p", { class: "ai-disclosure", "data-testid": "ai-disclosure" }, h("span", { class: "ai-chip" }, "AI"), t("empty.aiTitle")),
    h("details", { class: "disclosure", "data-testid": "capabilities" },
      h("summary", {}, t("empty.aiMore")),
      h("p", {}, t("empty.aiBody")),
      h("ul", { class: "cap-list" }, h("li", {}, t("empty.aiCan")), h("li", {}, t("empty.aiCannot")), h("li", {}, t("empty.aiAlways"))),
      h("h2", { class: "small-h" }, t("empty.scope")),
      h("p", {}, t("empty.scopeBody"))),
    h("h2", { class: "small-h" }, t("empty.examples")),
    h("div", { class: "examples" }, EXAMPLES.map((ex, i) =>
      h("button", { type: "button", class: "btn example", "data-key": `example-${i}`, onclick: () => { S.draft = L(ex); render({ focus: "prompt" }); } }, L(ex)))),
    h("p", { class: "muted" }, t("empty.exampleNote")),
  );
}

function renderMessage(msg) {
  const isAgent = msg.who === "agent";
  return h("li", { class: `msg ${isAgent ? "msg-agent" : "msg-user"}${msg.final ? " msg-final" : ""}` },
    h("div", { class: "msg-head" },
      isAgent ? h("img", { class: "avatar", src: "../../../ui/packages/components/src/primitives/brand/e-agent-mark.svg", alt: "", width: 20, height: 20 }) : null,
      h("span", { class: "author" }, isAgent ? t("messages.agent") : t("messages.you")),
      msg.label ? h("span", { class: `origin-label${msg.final ? " agent-words" : ""}`, "data-testid": msg.final ? "agent-words-msg" : null }, t(msg.label)) : null),
    h("p", { class: "msg-text" }, L(msg.text)));
}

function runActions(r, latest) {
  const openKey = `open-${r.n}`;
  const label = r.decision === "pending" ? t("run.openDecision") : r.result ? t("run.openResult") : t("run.open");
  const isOpen = S.ws.open && S.ws.run === r.n;
  return h("div", { class: "run-actions" },
    h("button", { type: "button", class: `btn${r.decision === "pending" ? " btn-primary" : ""}`, "data-key": openKey, "aria-controls": "workspace", "aria-expanded": String(isOpen), "data-testid": `open-run-${r.n}`, onclick: () => (isOpen ? closeWorkspace() : openWorkspace(r.n, null, openKey)) }, label),
    latest && r.active ? h("button", { type: "button", class: "btn btn-stop", "data-key": `stop-card-${r.n}`, "data-testid": "stop-card", onclick: stop }, h("span", { class: "stop-square", "aria-hidden": "true" }), t("run.cancel")) : null);
}

function renderRun(r, latest, m) {
  const folded = S.variant === "a2" && !latest && !S.showMsgs[r.n];
  const li = h("li", { class: `run-group${latest ? " latest" : ""}${folded ? " folded" : ""}`, "data-run": r.n, "aria-labelledby": `run-${r.n}-title` });
  li.append(h("p", { class: "run-gutter", "aria-hidden": "true" }, `${t("run")} ${r.n}`));
  if (!folded) li.append(h("ol", { class: "messages" }, r.msgs.map(renderMessage)));
  if (latest && S.state === "running") {
    // Activity from recorded events only (EA-5): the last recorded event, no progress estimate.
    const lastEv = r.events[r.events.length - 1];
    li.append(h("p", { class: "working-line", "data-testid": "working-line" }, h("span", { class: "badge-marker", "aria-hidden": "true" }, MARKER.progress), `${t("status.RUNNING")} · ${lastEv[0]} ${L(lastEv[1])}`));
  }
  const card = h("article", { class: `run-card tone-${r.tone}`, id: `run-card-${r.n}`, tabindex: "-1", "data-key": `run-card-${r.n}`, "data-testid": `run-card-${r.n}`, "aria-labelledby": `run-${r.n}-title` },
    h("header", { class: "run-card-head" },
      h("span", { class: "run-num" }, `${t("run")} ${r.n}`),
      h("h2", { class: "run-title", id: `run-${r.n}-title` }, L(r.title)),
      badge(r.tone, t(r.statusKey), { "data-testid": `run-status-${r.n}` })),
    r.line && !folded ? h("p", { class: "run-line" }, L(r.line)) : null,
    S.variant === "a3" && !folded ? renderRichCard(r) : null,
    h("div", { class: "run-card-foot" },
      S.variant === "a2" && !latest
        ? h("button", { type: "button", class: "btn btn-quiet", "data-key": `msgs-${r.n}`, "aria-expanded": String(!folded), onclick: () => { S.showMsgs[r.n] = !S.showMsgs[r.n]; render({ focus: `msgs-${r.n}` }); } }, folded ? `${t("run.showMessages")} (${r.msgs.length})` : t("run.hideMessages"))
        : null,
      runActions(r, latest)));
  li.append(card);
  return li;
}

function renderRichCard(r) {
  const parts = [];
  if (r.carried?.length) parts.push(h("p", { class: "carried-inline" }, `${t("carried.title")}: `, r.carried.map(n => h("a", { href: `#run-card-${n}`, onclick: e => { e.preventDefault(); focusRun(n); } }, `${t("run")} ${n}`)), h("span", { class: "muted" }, ` · ${t("carried.note")}`)));
  if (r.result === "grounded") parts.push(h("p", { class: "muted small" }, t("outcome.groundedExplain")));
  if (r.result === "verified") parts.push(h("p", { class: "muted small" }, `${t("outcome.records")}: PO-SAMPLE-0042 (${t("sample")})`));
  return parts.length ? h("div", { class: "run-rich" }, parts) : null;
}
function focusRun(n) {
  if (S.ws.open && !wide()) S.ws = { ...S.ws, open: false };
  render({ focus: `run-card-${n}` });
}

function renderComposer(m) {
  const form = h("form", { class: "composer", id: "composer", "aria-label": t("composer.label"), onsubmit: e => { e.preventDefault(); send(); } });
  const placeholder = m.composer === "answer" ? t("composer.answerPlaceholder") : m.runs.length ? t("composer.replyPlaceholder") : t("composer.placeholder");
  const submitLabel = m.composer === "answer" ? (m.answerKind === "question" ? t("composer.answer") : t("composer.reply")) : m.runs.length ? t("composer.reply") : t("composer.submit");
  const refusal = S.refusal ? renderRefusal(m) : null;
  const ta = h("textarea", { id: "prompt", "data-key": "prompt", rows: 2, placeholder, "aria-describedby": [S.refusal ? "refusal-hint" : null, "composer-help"].filter(Boolean).join(" "),
    oninput: e => { S.draft = e.target.value; },
    onkeydown: e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } } });
  ta.value = S.draft;
  const answering = m.composer === "answer"
    ? h("p", { class: "answering", "data-testid": "answering" }, `${t("composer.answering")} ${m.answering} · `, badge("attention", t(m.answerKind === "question" ? "status.WAITING_INPUT" : "status.WAITING_INPUT.reply")))
    : null;
  const frame = h("div", { class: `composer-frame${S.refusal ? " refused" : ""}` },
    S.variant === "a1" ? refusal : null,
    answering,
    h("label", { for: "prompt", class: "sr-only" }, t("composer.label")),
    ta,
    h("div", { class: "composer-row" },
      renderContext(true),
      h("span", { class: "help", id: "composer-help" }, t("composer.help")),
      h("button", { type: "submit", class: "btn btn-primary send", "data-key": "send" }, submitLabel)),
    S.variant === "a2" ? refusal : null);
  if (S.variant === "a3" && refusal) form.append(refusal);
  form.append(frame);
  if (S.protoNote) form.append(h("p", { class: "proto-note", role: "status" }, L(S.protoNote)));
  form.append(renderStopSlot(m));
  return form;
}

function renderContext(threadMode) {
  return h("details", { class: "context" },
    h("summary", { class: "btn btn-quiet", "data-key": "context" }, t("context.button")),
    h("div", { class: "context-pop" },
      h("p", { class: "small-h" }, t("context.title")),
      h("p", {}, t("context.sentNoHost")),
      h("p", { "data-testid": "context-used" }, threadMode ? t("context.noHostThread") : t("context.noHost"))));
}

function renderRefusal(m) {
  const key = S.refusal.kind === "busy" ? "conversation.refusedBusy" : "conversation.refusedQuestion";
  const details = h("details", { class: "refusal-details" },
    h("summary", {}, t("refused.details")),
    h("dl", {}, h("dt", {}, t("refused.reference")), h("dd", { class: "mono" }, S.refusal.ref),
      h("dt", {}, "server"), h("dd", { class: "mono" }, `409 · "${S.refusal.server}"`)));
  const latest = m.runs[m.runs.length - 1];
  const link = S.variant === "a3" && latest
    ? S.refusal.kind === "busy" && latest.decision === "pending"
      ? h("button", { type: "button", class: "btn", "data-key": "refusal-go", onclick: () => openWorkspace(latest.n, "decision", "refusal-go") }, t("refused.goDecision"))
      : h("button", { type: "button", class: "btn", "data-key": "refusal-go", onclick: () => focusRun(latest.n) }, t("refused.readAgain"))
    : null;
  return h("div", { class: `refusal refusal-${S.variant}`, role: "alert", "data-testid": "refusal" },
    h("p", { class: "refusal-hint", id: "refusal-hint" }, h("span", { class: "badge-marker", "aria-hidden": "true" }, MARKER.attention), t(key)),
    h("p", { class: "refusal-kept" }, t("refused.kept")),
    link, details);
}

function renderStopSlot(m) {
  const latest = m.runs[m.runs.length - 1];
  const active = latest?.active;
  return h("div", { class: "stop-slot", "data-testid": "stop-slot", "data-active": String(Boolean(active)) },
    latest ? h("span", { class: "stop-run" }, `${t("run")} ${latest.n}`) : null,
    latest ? badge(latest.tone, t(latest.statusKey)) : null,
    active
      ? h("button", { type: "button", class: "btn btn-stop", "data-key": "stop", "data-testid": "stop", onclick: stop }, h("span", { class: "stop-square", "aria-hidden": "true" }), t("run.cancel"))
      : h("span", { class: "stop-off" },
        h("button", { type: "button", class: "btn btn-stop", disabled: true, "data-testid": "stop", "aria-describedby": "stop-why" }, h("span", { class: "stop-square", "aria-hidden": "true" }), t("run.cancel")),
        h("span", { class: "muted", id: "stop-why" }, t("run.nothingRunning"))));
}

// ---------- Workspace ----------
function renderWorkspace(m) {
  const aside = h("aside", { id: "workspace", class: "workspace", "aria-labelledby": "ws-heading", hidden: !S.ws.open, "data-testid": "workspace",
    onkeydown: e => { if (e.key === "Escape") { e.stopPropagation(); if (S.confirm) { S.confirm = false; render({ focus: "approve" }); } else closeWorkspace(); } } });
  if (!S.ws.open) return aside;
  const r = m.runs.find(x => x.n === S.ws.run);
  if (!r) return aside;
  aside.append(
    h("div", { class: "ws-head" },
      h("button", { type: "button", class: "btn btn-quiet ws-back", "data-key": "ws-back", onclick: closeWorkspace }, `← ${t("ws.back")}`),
      h("p", { class: "ws-kicker" }, `${t("ws.label")} · ${t("run")} ${r.n}`),
      h("h2", { id: "ws-heading", tabindex: "-1", "data-key": "ws-heading" }, L(r.title)),
      badge(r.tone, t(r.statusKey)),
      h("button", { type: "button", class: "btn btn-quiet ws-close", "data-key": "ws-close", "data-testid": "ws-close", "aria-label": t("ws.close"), title: t("ws.close"), onclick: closeWorkspace }, h("span", { "aria-hidden": "true" }, "✕"))),
    renderTabs(r),
  );
  return aside;
}

function renderTabs(r) {
  const tabs = r.tabs;
  const sel = tabs.includes(S.ws.tab) ? S.ws.tab : tabs[0];
  const choose = (tab, focus) => { S.ws.tab = tab; S.confirm = false; render({ focus: focus ? `tab-${tab}` : undefined }); };
  const list = h("div", { role: "tablist", class: "tabs", "aria-label": t("ws.label") },
    tabs.map((tab, i) => h("button", {
      type: "button", role: "tab", id: `tab-${tab}`, "data-key": `tab-${tab}`, "aria-selected": String(tab === sel), "aria-controls": `panel-${tab}`, tabindex: tab === sel ? "0" : "-1",
      onclick: () => choose(tab, true),
      onkeydown: e => {
        const k = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (k) { e.preventDefault(); choose(tabs[(i + k + tabs.length) % tabs.length], true); }
        if (e.key === "Home") { e.preventDefault(); choose(tabs[0], true); }
        if (e.key === "End") { e.preventDefault(); choose(tabs[tabs.length - 1], true); }
      },
    }, t(`tab.${tab}`))));
  const panel = h("div", { role: "tabpanel", id: `panel-${sel}`, "aria-labelledby": `tab-${sel}`, class: "ws-panel", tabindex: "0" });
  if (sel === "decision") panel.append(renderApproval(r));
  if (sel === "result") panel.append(renderResult(r));
  if (sel === "sources") panel.append(renderSources(r));
  if (sel === "activity") panel.append(renderActivity(r));
  return h("div", { class: "ws-body" }, list, panel);
}

function renderApproval(r, { inline = false } = {}) {
  const decided = r.decision === "approved" || r.decision === "rejected";
  const sec = h("section", { class: "approval", "aria-labelledby": "appr-title", "data-testid": "approval-card" },
    h("p", { class: "kicker" }, t("approval.kicker")),
    h("h3", { id: "appr-title" }, t("approval.title")),
    h("p", {}, t("approval.description")),
    h("dl", { class: "appr-meta" },
      h("dt", {}, t("approval.capability")), h("dd", {}, L(APPROVAL.capability)),
      h("dt", {}, t("approval.connection")), h("dd", {}, L(APPROVAL.connection)),
      h("dt", {}, t("approval.credential")), h("dd", {}, L(APPROVAL.actsAs)),
      h("dt", {}, t("approval.expires")), h("dd", {}, L(APPROVAL.expires))),
    h("table", { class: "appr-fields" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, t("approval.field")), h("th", { scope: "col" }, t("approval.current")), h("th", { scope: "col" }, t("approval.proposed")))),
      h("tbody", {}, APPROVAL.fields.map(f => h("tr", {}, h("th", { scope: "row" }, L(f.f)), h("td", { class: "muted", "data-label": t("approval.current") }, f.cur ? L(f.cur) : t("approval.unknown")), h("td", { "data-label": t("approval.proposed") }, L(f.val)))))),
    h("p", { class: "reversible" }, h("strong", {}, `${t("approval.reversible")}: `), L(APPROVAL.reversible)),
    h("div", { class: "findings" },
      h("h4", {}, t("approval.findings")),
      h("p", {}, badge("verified", t("approval.allChecks"))),
      h("ul", {}, APPROVAL.findings.map(f => h("li", {}, L(f))))),
  );
  if (decided) {
    sec.append(h("p", { class: "decided", role: "status" }, badge(r.decision === "approved" ? "neutral" : "neutral", t(r.decision === "approved" ? "approval.approved" : "approval.rejected"))));
    return sec;
  }
  if (!S.confirm) {
    sec.append(h("div", { class: "appr-actions" },
      h("button", { type: "button", class: "btn btn-primary", "data-key": "approve", "data-testid": "approve", onclick: () => { S.confirm = true; render({ focus: "confirm-prompt" }); } }, t("approval.approve")),
      h("button", { type: "button", class: "btn", "data-key": "reject", onclick: () => enter("rejected") }, t("approval.reject"))));
  } else {
    sec.append(h("div", { class: "confirm", role: "group", "aria-labelledby": "confirm-prompt" },
      h("p", { id: "confirm-prompt", tabindex: "-1", "data-key": "confirm-prompt" }, t("approval.confirmPrompt")),
      h("div", { class: "appr-actions" },
        h("button", { type: "button", class: "btn btn-primary", "data-key": "confirm", "data-testid": "confirm", onclick: () => { enter("approved", { keepDraft: true }); if (wide() || inline) openWorkspace(2, "decision", "open-2"); } }, t("approval.confirm")),
        h("button", { type: "button", class: "btn", "data-key": "back", onclick: () => { S.confirm = false; render({ focus: "approve" }); } }, t("approval.back")))));
  }
  return sec;
}

function agentWords(text) {
  return h("figure", { class: "agent-words-block", "data-testid": "agent-words-result" },
    h("figcaption", {}, h("span", { class: "ai-chip" }, "AI"), h("strong", {}, `${t("outcome.agentText")} · `), t("messages.agentWords")),
    h("blockquote", {}, L(text)));
}

function renderResult(r) {
  const sec = h("section", { class: "result", "aria-labelledby": "result-h" }, h("h3", { id: "result-h" }, t("outcome.title")));
  if (r.result === "grounded") {
    sec.append(
      h("p", {}, badge("neutral", t("status.SUCCEEDED.grounded"), { "data-testid": "grounded-badge" })),
      h("p", { class: "explain-line", "data-testid": "grounded-explain" }, t("outcome.groundedExplain")),
      h("h4", {}, t("citation.title")),
      h("ol", { class: "citations" }, CITATIONS.map(c => c.unresolved
        ? h("li", { class: "citation unresolved" }, h("span", { class: "badge-marker", "aria-hidden": "true" }, MARKER.unknown), t("citation.unresolved"))
        : h("li", { class: "citation" },
          h("dl", {}, h("dt", {}, t("citation.record")), h("dd", {}, L(c.record)),
            h("dt", {}, t("citation.field")), h("dd", { class: "mono" }, c.field),
            h("dt", {}, t("citation.value")), h("dd", { class: "muted" }, t("citation.valueNotRecorded")))))),
      agentWords(TEXT.a_grounded),
      renderExplanation(r));
  } else if (r.result === "verified") {
    sec.append(
      h("p", {}, badge("verified", t("status.SUCCEEDED"), { "data-testid": "verified-badge" })),
      h("dl", { class: "kv" },
        h("dt", {}, t("outcome.records")), h("dd", {}, `PO-SAMPLE-0042 · ${t("sample")}`),
        VERIFIED_VALUES.map(([k, v]) => [h("dt", {}, `${t("outcome.values")} · ${L(k)}`), h("dd", {}, L(v))])),
      h("h4", {}, t("outcome.checks")),
      h("p", {}, badge("verified", t("outcome.VERIFIED")), " ", L(TEXT.r2_verified), " · 09:48"),
      agentWords(TEXT.a_verified),
      renderExplanation(r));
  } else if (r.result === "failed") {
    sec.append(
      h("p", {}, badge("failed", t("status.FAILED"))),
      h("p", { class: "fail-problem" }, L(TEXT.r2_failed)),
      h("dl", { class: "kv" },
        h("dt", {}, t("outcome.failedCause")), h("dd", {}, L(TEXT.failedCause)),
        h("dt", {}, t("outcome.failedNext")), h("dd", {}, L(TEXT.failedNext))),
      h("p", {}, h("strong", {}, t("outcome.nothingWritten"))));
  }
  return sec;
}

function renderExplanation(r) {
  const row = (k, ...v) => [h("dt", {}, t(k)), h("dd", {}, ...v)];
  const verified = r.result === "verified";
  return h("details", { class: "disclosure explanation", open: S.explainOpen, "data-testid": "explanation", ontoggle: e => (S.explainOpen = e.target.open) },
    h("summary", { "data-key": "explain" }, t("explain.open")),
    h("dl", { class: "explain-list" },
      row("explain.goal", L(r.n === 1 ? TEXT.u_short : TEXT.u_po)),
      row("explain.facts", h("ul", {}, (r.sources || []).map(s => h("li", {}, `${L(s.name)} · ${t("evidence.observed")} ${s.at}`)))),
      row("explain.rules", verified ? h("ul", {}, APPROVAL.findings.map(f => h("li", {}, L(f)))) : t("explain.none")),
      row("explain.proposal", verified ? L(APPROVAL.capability) : t("explain.none")),
      row("explain.rationale", verified ? h("span", {}, h("span", { class: "mono" }, "rat-sample-01"), ` · ${t("explain.rationaleIds")}`) : t("explain.none")),
      row("explain.approval", verified ? `${t("approval.approved")} · 09:47 · ${L(APPROVAL.actsAs)}` : t("explain.none")),
      row("explain.receipt", verified ? "PO-SAMPLE-0042 · 09:47" : t("explain.none")),
      row("explain.outcome", t(r.statusKey))));
}

function renderSources(r) {
  const sec = h("section", { class: "sources", "aria-labelledby": "sources-h" });
  if (r.carried?.length) {
    sec.append(h("div", { class: "carried", "data-testid": "carried" },
      h("p", {}, h("strong", {}, `${t("carried.title")}: `), r.carried.map(n => h("a", { href: `#run-card-${n}`, onclick: e => { e.preventDefault(); focusRun(n); } }, `${t("run")} ${n}`))),
      h("p", { class: "muted" }, t("carried.note"))));
  }
  sec.append(h("h3", { id: "sources-h" }, t("evidence.sources")),
    r.sources?.length
      ? h("ul", { class: "source-list" }, r.sources.map(s => h("li", {}, h("span", { class: "source-name" }, L(s.name)), h("span", { class: "muted" }, `${t("evidence.observed")} ${s.at} · ${s.complete ? t("evidence.complete") : t("evidence.partial")}`))))
      : h("p", { class: "muted" }, S.lang === "vi" ? "Lượt này chưa đọc nguồn nào." : "This run has read no sources yet."));
  return sec;
}

function renderActivity(r) {
  return h("section", { class: "activity", "aria-labelledby": "activity-h" },
    h("h3", { id: "activity-h" }, t("activity.title")),
    h("ol", { class: "events" }, r.events.map(([time, text]) => h("li", {}, h("time", {}, time), h("span", {}, L(text))))),
    r.result && r.result !== "failed" ? h("button", { type: "button", class: "btn", "data-key": "activity-explain", onclick: () => { S.ws.tab = "result"; S.explainOpen = true; render({ focus: "explain" }); } }, t("explain.open")) : null);
}

// ---------- Fallback, legacy and gallery ----------
function renderFallback() {
  // Today's per-run view: one run, the card in the conversation column, an inspector beside it
  // that cannot be closed, and the locked composer while a decision waits (ADR 0034 §2).
  const routeError = S.mode === "route-error";
  const shell = h("div", { class: "shell fallback", "data-state-sample": "fallback", "data-mode": S.mode });
  const runState = routeError ? "status.WAITING_INPUT.reply" : "status.WAITING_APPROVAL";
  const r = { n: 1, title: TEXT.u_fallback, statusKey: runState, tone: "attention", active: true, decision: "pending", events: ev(2, 8).filter((_, i) => i !== 1), sources: SOURCES[2], tabs: [] };
  const notice = S.mode === "features" ? h("p", { class: "notice", role: "status", "data-testid": "fallback-notice" }, t("fallback.featuresFailed")) : null;
  const col = h("main", { class: "thread-col per-run" },
    h("p", { class: "mode-line", "data-testid": "mode-line" }, t(`fallback.mode.${S.mode}`)),
    notice,
    h("div", { class: "thread-scroll" },
      h("ol", { class: "messages" }, [msgUser(TEXT.u_fallback), routeError ? msgReply(TEXT.a_fallbackReply) : null].filter(Boolean).map(renderMessage)),
      routeError ? null : renderApproval(r, { inline: true })),
    renderFallbackComposer(r, routeError));
  const inspector = h("aside", { class: "inspector", "aria-label": `${t("tab.sources")} · ${t("tab.activity")}` }, renderSources({ ...r, carried: [] }), renderActivity(r));
  shell.append(renderHeader(TEXT.u_fallback, { nav: false }), col, inspector);
  return shell;
}

function renderFallbackComposer(r, routeError) {
  const form = h("form", { class: "composer", id: "composer", "aria-label": t("composer.label"), onsubmit: e => { e.preventDefault(); if (routeError) render({ focus: "prompt" }); } });
  const ta = h("textarea", { id: "prompt", "data-key": "prompt", rows: 2, disabled: !routeError, placeholder: routeError ? t("composer.replyPlaceholder") : "", "aria-describedby": "composer-help", oninput: e => (S.draft = e.target.value) });
  ta.value = S.draft;
  form.append(...[
    routeError ? h("div", { class: "refusal refusal-a1", role: "alert", "data-testid": "route-error" }, h("p", { class: "refusal-hint" }, h("span", { class: "badge-marker", "aria-hidden": "true" }, MARKER.failed), t("fallback.routeError"))) : null,
    h("div", { class: "composer-frame" },
      h("label", { for: "prompt", class: "sr-only" }, t("composer.label")), ta,
      h("div", { class: "composer-row" }, renderContext(false), h("span", { class: "help", id: "composer-help" }, routeError ? t("composer.help") : t("composer.locked")), h("button", { type: "submit", class: "btn btn-primary send", disabled: !routeError, "data-key": "send" }, t("composer.reply")))),
    renderStopSlot({ runs: [r] })].filter(Boolean));
  return form;
}

function renderLegacyMain() {
  const lr = TEXT.legacyRuns[0];
  return h("div", { class: "thread-scroll legacy-main", "data-testid": "legacy-main" },
    h("p", { class: "mode-line", tabindex: "-1", "data-key": "legacy-heading-main" }, t("legacy.title")),
    h("ol", { class: "messages" }, renderMessage(msgUser(TEXT.legacyMsg))),
    h("article", { class: "run-card tone-neutral" },
      h("header", { class: "run-card-head" }, h("h2", { class: "run-title" }, L(lr.title)), badge(lr.nowTone, t(lr.now))),
      h("p", { class: "run-line" }, L(TEXT.legacyEnd)),
      h("p", { class: "muted small" }, `${t("legacy.now")} ${t("legacy.lastSeenWas")}: ${t(lr.last)}`)));
}

function renderGallery() {
  return h("section", { class: "gallery", "aria-labelledby": "gallery-h", "data-testid": "gallery" },
    h("h1", { id: "gallery-h", class: "gallery-h" }, t("gallery.title")),
    h("p", { class: "muted" }, t("gallery.note")),
    h("ul", { class: "gallery-list" }, GALLERY.map((g, i) =>
      h("li", { class: `run-card tone-${g.tone}`, "data-normative": g.normative },
        h("header", { class: "run-card-head" }, h("span", { class: "run-num" }, g.normative), badge(g.tone, t(g.key))),
        g.body ? h("p", { class: "run-line" }, t(g.body)) : null,
        h("div", { class: "run-actions" },
          g.action ? btn(t(g.action), { "data-key": `g-act-${i}` }) : null,
          g.stop === "on" ? h("button", { type: "button", class: "btn btn-stop", "data-key": `g-stop-${i}`, "data-testid": "gallery-stop" }, h("span", { class: "stop-square", "aria-hidden": "true" }), t("run.cancel"))
            : h("span", { class: "stop-off" }, h("button", { type: "button", class: "btn btn-stop", disabled: true, "data-testid": "gallery-stop", "aria-describedby": `g-why-${i}` }, h("span", { class: "stop-square", "aria-hidden": "true" }), t("run.cancel")),
              h("span", { class: "muted", id: `g-why-${i}` }, g.stop === "reconcile" ? t("run.noStopReconcile") : t("run.nothingRunning"))))))));
}

// ---------- Global keys and the prototype "next event" control ----------
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && S.navOpen && !document.getElementById("workspace")?.contains(e.target)) {
    S.navOpen = false;
    render({ focus: "nav-toggle" });
  }
});
document.getElementById("proto-next").addEventListener("click", () => {
  const m = model(S.state);
  if (m.next) enter(m.next);
});
function syncNext() {
  const m = S.state === "fallback" ? {} : model(S.state);
  const b = document.getElementById("proto-next");
  b.hidden = !m.next;
  b.textContent = m.next === "verified" ? t("proto.toVerified") : t("proto.next");
}

window.__mock = {
  states: STATE_IDS,
  variants: VARIANTS.map(v => v.id),
  get current() { return { ...S, ws: { ...S.ws } }; },
  enter,
};
enter(S.state, { keepDraft: false });
