/**
 * Reference custom UI (UI architecture §5 tier T4): no framework, only ui-core and
 * the client. All text goes through textContent; nothing is parsed as HTML.
 */
import "@e-agent/tokens/tokens.css";
import "./style.css";
import { EAgentClient } from "@e-agent/client";
import {
  canRequestApprove,
  formatFieldValue,
  resolveLocale,
  RunController,
  segmentText,
  selectTimeline,
  translate,
  type ControllerState,
} from "@e-agent/ui-core";

const params = new URLSearchParams(location.search);
const locale = resolveLocale(params.get("lang") ?? navigator.language);
document.documentElement.lang = locale;
document.documentElement.dataset["theme"] = params.get("theme") ?? "light";
const t = (key: string) => translate(locale, key);
const controller = new RunController({ client: new EAgentClient(), locale, storageKey: "e-agent.reference.run" });

type Attrs = Record<string, string | boolean | undefined>;
function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: (Node | string | null)[]): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === false) continue;
    node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children) if (c !== null) node.append(typeof c === "string" ? document.createTextNode(c) : c);
  return node;
}
function button(label: string, testid: string, onClick: () => void, disabled = false): HTMLButtonElement {
  const b = el("button", { type: "button", "data-testid": testid, disabled });
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

const app = document.getElementById("app") as HTMLElement;
const header = el("section");
const messages = el("section", { "data-testid": "messages" });
const approval = el("section", { "data-testid": "approval", "aria-label": t("approval.title") });
const outcome = el("section", { "data-testid": "outcome" });
const timeline = el("section", { "data-testid": "timeline" });
const evidence = el("section", { "data-testid": "evidence" });

// Composer is built once so typing and focus survive re-renders.
const input = el("input", { "data-testid": "composer-input", "aria-label": t("composer.label"), placeholder: t("composer.placeholder") });
const submit = el("button", { type: "submit", "data-testid": "composer-submit" }, t("composer.submit"));
const form = el("form", { "data-testid": "composer" }, input, submit);
form.addEventListener("submit", (e) => {
  e.preventDefault();
  const task = input.value;
  if (task.trim()) void controller.start(task).then(() => (input.value = ""));
});
app.append(header, messages, form, approval, outcome, timeline, evidence);

function renderHeader(s: ControllerState) {
  const state = s.view.run ? el("span", { "data-testid": "run-state", "data-state": s.view.run.state }, `${t("run.state")}: ${s.view.run.state}`) : null;
  header.replaceChildren(
    el("h1", {}, `${t("app.title")} — reference`),
    el("span", { "data-testid": "connection-status", "data-status": s.connection, role: "status" }, t(`connection.${s.connection}`)),
    " ",
    state ?? "",
  );
}

function renderMessages(s: ControllerState) {
  const children: (Node | string)[] = [el("h2", {}, t("messages.title"))];
  if (!s.view.run) children.push(el("p", {}, t("messages.empty")));
  else children.push(el("p", { "data-testid": "run-task" }, s.view.run.task));
  if (s.view.finalMessage) {
    const msg = el("div", { "data-testid": "final-message" }, `${t("messages.final")}: `);
    for (const seg of segmentText(s.view.finalMessage)) {
      if (seg.kind === "link") msg.append(el("a", { href: seg.href, rel: "noopener noreferrer nofollow", target: "_blank", referrerpolicy: "no-referrer" }, seg.text));
      else if (seg.kind === "image") msg.append(el("span", { "data-testid": "blocked-image" }, `[${t("image.blocked")}: ${seg.alt} ${seg.url}]`));
      else msg.append(seg.text);
    }
    children.push(msg);
  }
  if (s.error) children.push(el("p", { class: "alert", role: "alert", "data-testid": "error" }, s.error));
  messages.replaceChildren(...children);
}

function renderApproval(s: ControllerState) {
  const a = s.approval;
  const p = a.presentation;
  approval.dataset["phase"] = p ? a.phase : "idle";
  const out: (Node | string)[] = [el("h2", {}, t("approval.title"))];
  if (!p || a.phase === "idle") {
    out.push(el("p", {}, t("approval.none")));
    approval.replaceChildren(...out);
    return;
  }
  out.push(el("p", { "data-testid": "approval-capability" }, p.contract_id), el("p", {}, `${t("approval.credential")}: ${p.credential_subject}`));
  const rows = p.material_fields.map((f) =>
    el(
      "tr",
      { "data-testid": "material-field", "data-path": f.path, "data-changed": String(f.changed) },
      el("th", { scope: "row" }, f.path),
      el("td", {}, formatFieldValue(f.path, f.value, locale), f.changed ? ` (${t("approval.changed")})` : ""),
      el("td", {}, f.changed ? (f.previous_value ?? "—") : ""),
    ),
  );
  out.push(el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, t("approval.field")), el("th", {}, t("approval.value")), el("th", {}, t("approval.previous")))), el("tbody", {}, ...rows)));
  out.push(el("h3", {}, t("approval.findings")));
  out.push(el("ul", {}, ...p.findings.map((f) => el("li", { "data-testid": "finding", "data-status": f.status }, `${f.status} ${f.rule_id}: ${f.message}`))));
  if (a.digestOk === false) out.push(el("p", { class: "alert", role: "alert", "data-testid": "approval-digest-mismatch" }, t("approval.digestMismatch")));
  if (a.phase === "expired") out.push(el("p", { class: "alert", role: "alert", "data-testid": "approval-expired" }, t("approval.expired")));
  if (a.phase === "stale") {
    out.push(el("p", { class: "alert", role: "alert", "data-testid": "approval-stale" }, t("approval.stale")));
    out.push(button(t("approval.reviewAgain"), "approval-review-again", () => controller.reviewAgain()));
  }
  if (a.phase === "approved") out.push(el("p", { role: "status", "data-testid": "approval-approved" }, t("approval.approved")));
  if (a.phase === "rejected") out.push(el("p", { role: "status", "data-testid": "approval-rejected" }, t("approval.rejected")));
  if (a.phase === "reviewing") {
    out.push(button(t("approval.approve"), "approval-approve", () => controller.requestConfirm(), !canRequestApprove(a)));
    out.push(button(t("approval.reject"), "approval-reject", () => void controller.reject()));
  }
  let prompt: HTMLElement | null = null;
  if (a.phase === "confirming") {
    prompt = el("div", { tabindex: "-1", "data-testid": "approval-confirm-prompt" }, el("p", {}, t("approval.confirmPrompt")));
    prompt.append(
      button(t("approval.confirm"), "approval-confirm", () => void controller.approve(), !controller.canApprove()),
      button(t("approval.back"), "approval-back", () => controller.back()),
      button(t("approval.reject"), "approval-reject", () => void controller.reject()),
    );
    out.push(prompt);
  }
  approval.replaceChildren(...out);
  prompt?.focus(); // focus the prompt, never the confirm button
}

function renderOutcome(s: ControllerState) {
  const run = s.view.run;
  if (!run) return outcome.replaceChildren();
  const out: (Node | string)[] = [
    el("h2", {}, t("outcome.title")),
    el("p", { "data-testid": "outcome-state", "data-state": run.state }, `${run.state}${run.reason ? ` — ${run.reason}` : ""}`),
    el("ul", {}, ...s.view.actions.map((a) => el("li", { "data-testid": "action", "data-state": a.state }, `${a.contract_id}: ${a.state}`))),
  ];
  if (run.state === "NEEDS_RECONCILIATION") {
    out.push(el("p", { class: "alert", role: "alert", "data-testid": "outcome-unresolved" }, t("outcome.unresolved")));
    out.push(button(t("outcome.reconcile"), "outcome-reconcile", () => void controller.reconcile()));
  }
  outcome.replaceChildren(...out);
}

function renderTimeline(s: ControllerState) {
  const items = selectTimeline(s.view).map((i) =>
    el("li", { "data-testid": "timeline-item", "data-type": i.type, "data-supported": String(i.supported) }, `${t(i.labelKey)}${i.detail ? ` · ${i.detail}` : ""}`),
  );
  timeline.replaceChildren(el("h2", {}, t("timeline.title")), el("ol", {}, ...items));
}

function renderEvidence(s: ControllerState) {
  const run = s.view.run;
  const done = run && ["SUCCEEDED", "FAILED", "CANCELLED", "NEEDS_RECONCILIATION"].includes(run.state);
  const out: (Node | string)[] = [el("h2", {}, t("evidence.title"))];
  if (s.evidence) out.push(el("pre", { "data-testid": "evidence-bundle" }, JSON.stringify(s.evidence, null, 2)));
  else if (done) out.push(button(t("evidence.load"), "evidence-load", () => void controller.loadEvidence()));
  else out.push(el("p", {}, t("evidence.empty")));
  evidence.replaceChildren(...out);
}

// Re-render a section only when its inputs change, so focus is not lost mid-review.
let prev: ControllerState | null = null;
function render() {
  const s = controller.getState();
  if (!prev || prev.connection !== s.connection || prev.view.run !== s.view.run) renderHeader(s);
  if (!prev || prev.view.run !== s.view.run || prev.view.finalMessage !== s.view.finalMessage || prev.error !== s.error) renderMessages(s);
  if (!prev || prev.approval !== s.approval) renderApproval(s);
  if (!prev || prev.view.run !== s.view.run || prev.view.actions !== s.view.actions) renderOutcome(s);
  if (!prev || prev.view.events !== s.view.events) renderTimeline(s);
  if (!prev || prev.view.run !== s.view.run || prev.evidence !== s.evidence) renderEvidence(s);
  submit.disabled = s.busy;
  prev = s;
}
controller.subscribe(render);
render();
void controller.init();
