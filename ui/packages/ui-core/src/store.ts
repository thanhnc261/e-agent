/**
 * Event-sourced run view (UI architecture §3 L3). The server snapshot is the base;
 * events are ordered deltas deduplicated by ``sequence``. A gap or an unknown event
 * type never guesses: it asks the controller for a fresh snapshot.
 */
import type { ActionSummary, ConversationSnapshot, RunEvent, RunRecord, RunSnapshot, TextFrame } from "@e-agent/client";

/**
 * Conversation bookkeeping (ADR 0023 §11): ids, counts and digests the server records for
 * comparison and evidence. They are known, kept in the view and advance its sequence, so gap
 * detection still holds, but no timeline row shows them: `shadow` keeps today's view.
 */
export const HIDDEN_EVENT_TYPES: ReadonlySet<string> = new Set([
  "conversation.compared",
  "conversation.context_carried",
  "conversation.shadow_failed",
]);

export const KNOWN_EVENT_TYPES: ReadonlySet<string> = new Set([
  ...HIDDEN_EVENT_TYPES,
  "run.created",
  "run.state_changed",
  "read.recorded",
  "read.rejected",
  "proposal.created",
  "validation.completed",
  "approval.requested",
  "approval.decided",
  "connect.required",
  "input.requested",
  "input.received",
  "action.reserved",
  "action.dispatching",
  "action.receipt_recorded",
  "action.unknown",
  "reconciliation.completed",
  "outcome.reported",
  "message.final",
  "budget.exhausted",
  "run.cancel_requested",
  "run.terminal",
  "feature.fallback",
  "ir.plan_compiled",
  "ir.shadow_failed",
  "ir.lineage_resolved",
  "ir.step_verified",
]);

/** Events after which the snapshot (actions, pending approval) must be re-read. */
const SNAPSHOT_TRIGGERS: ReadonlySet<string> = new Set([
  "approval.requested",
  "approval.decided",
  "proposal.created",
  "action.receipt_recorded",
  "outcome.reported",
  "reconciliation.completed",
  "run.terminal",
  "input.requested",
  "input.received",
]);

export interface RunView {
  run: RunRecord | null;
  events: RunEvent[];
  lastSequence: number;
  actions: ActionSummary[];
  finalMessage: string | null;
  streamingText: string;
  textStreamId: string | null;
  textOffset: number;
  question: string | null;
  /** Set when the view may be missing information; the controller re-fetches. */
  needsSnapshot: boolean;
  unsupportedEvents: number;
}

export const emptyRunView: RunView = {
  run: null,
  events: [],
  lastSequence: 0,
  actions: [],
  finalMessage: null,
  streamingText: "",
  textStreamId: null,
  textOffset: 0,
  question: null,
  needsSnapshot: false,
  unsupportedEvents: 0,
};

export type RunViewAction =
  | { type: "snapshot"; snapshot: RunSnapshot }
  | { type: "events"; events: RunEvent[] }
  | { type: "reset" }
  | { type: "text"; frame: TextFrame };

function applyEvent(view: RunView, event: RunEvent): RunView {
  if (event.sequence <= view.lastSequence) return view; // duplicate (replay/reconnect)
  if (event.sequence !== view.lastSequence + 1) return { ...view, needsSnapshot: true }; // gap
  const next: RunView = { ...view, events: [...view.events, event], lastSequence: event.sequence };
  const type = event.type as string;
  if (event.schema_version !== "1" || !KNOWN_EVENT_TYPES.has(type)) {
    return { ...next, needsSnapshot: true, unsupportedEvents: view.unsupportedEvents + 1 };
  }
  const payload = event.payload ?? {};
  if (type === "run.state_changed" && next.run) {
    const state = payload["to"] ?? payload["state"];
    if (typeof state !== "string" || !RUN_STATES.has(state)) return { ...next, needsSnapshot: true };
    next.run = { ...next.run, state: state as RunRecord["state"] };
    if (state === "WAITING_INPUT") next.streamingText = ""; // the state change commits after input.requested
  }
  if (type === "message.final" && typeof payload["text"] === "string") {
    next.finalMessage = payload["text"];
    next.streamingText = "";
  }
  if (type === "input.requested" && typeof payload["question"] === "string") {
    next.question = payload["question"];
    next.streamingText = ""; // the recorded question is the message; never show it twice
  }
  if (type === "input.received") next.question = null;
  if (SNAPSHOT_TRIGGERS.has(type)) next.needsSnapshot = true;
  return next;
}

export function reduceRunView(view: RunView, action: RunViewAction): RunView {
  switch (action.type) {
    case "reset":
      return emptyRunView;
    case "text": {
      if (TERMINAL_STATES.has(view.run?.state ?? "") || view.run?.state === "WAITING_INPUT") return view;
      const frame = action.frame;
      const sameStream = frame.stream_id === view.textStreamId;
      if (sameStream && frame.offset <= view.textOffset) return view;
      if (!frame.reset && (!sameStream || frame.offset !== view.textOffset + 1)) {
        return { ...view, needsSnapshot: true };
      }
      return { ...view, textStreamId: frame.stream_id, textOffset: frame.offset,
        streamingText: frame.reset ? frame.text : view.streamingText + frame.text };
    }
    case "snapshot":
      return {
        ...view,
        run: action.snapshot.run,
        streamingText: TERMINAL_STATES.has(action.snapshot.run.state) || action.snapshot.run.state === "WAITING_INPUT" ? "" : view.streamingText,
        actions: action.snapshot.actions,
        needsSnapshot: false,
      };
    case "events": {
      let next = view;
      for (const e of [...action.events].sort((a, b) => a.sequence - b.sequence)) {
        next = applyEvent(next, e);
      }
      return next;
    }
  }
}

export interface TimelineItem {
  sequence: number;
  type: string;
  labelKey: string;
  occurredAt: string;
  supported: boolean;
  detail: string | null;
  /**
   * For a run state change: the server's states, so a UI can label them. `toReply` and
   * `fromReply` mark a WAITING_INPUT entered after a conversational reply (ADR 0022), so
   * the row reads like the composer and the sidebar ("Your turn"), never a second name.
   */
  transition?: { from: string; to: string; toReply?: true; fromReply?: true };
}

function legacyTransition(p: Record<string, unknown>): { from: string; to: string } {
  const text = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
  return { from: text(p["from"]) ?? "unknown", to: text(p["to"]) ?? text(p["state"]) ?? "unknown" };
}

/** Plain-data timeline; detail is a short, non-HTML string. */
export function selectTimeline(view: RunView): TimelineItem[] {
  // The kind of the last recorded request, and whether the current wait is on a reply.
  let lastRequest: string | null = null;
  let waitingOnReply = false;
  const shown = view.events.filter(e => !(e.schema_version === "1" && HIDDEN_EVENT_TYPES.has(e.type as string)));
  return shown.map((e) => {
    const type = e.type as string;
    const supported = e.schema_version === "1" && KNOWN_EVENT_TYPES.has(type);
    const p = e.payload ?? {};
    let detail: string | null = null;
    // Rows written before ADR 0031 carry only `state`; an absent `from` stays "unknown", never "undefined".
    if (supported && type === "input.requested") lastRequest = p["kind"] === "reply" ? "reply" : "other";
    if (supported && type === "input.received") lastRequest = null;
    let transition: TimelineItem["transition"] | null = null;
    if (supported && type === "run.state_changed") {
      const states = legacyTransition(p);
      const fromReply = states.from === "WAITING_INPUT" && waitingOnReply;
      const toReply = states.to === "WAITING_INPUT" && lastRequest === "reply";
      waitingOnReply = toReply;
      transition = { ...states, ...(fromReply ? { fromReply: true } : {}), ...(toReply ? { toReply: true } : {}) };
    }
    if (transition) detail = `${transition.from} → ${transition.to}`;
    else if (supported && (type === "validation.completed" || type === "outcome.reported")) detail = String(p["status"] ?? "");
    else if (supported && type === "approval.decided") detail = String(p["decision"] ?? "");
    else if (supported && (type === "proposal.created" || type === "read.recorded")) detail = String(p["contract_id"] ?? "");
    else if (supported && type === "read.rejected") detail = typeof p["code"] === "string" ? p["code"] : null;
    else if (supported && (type === "feature.fallback" || type === "ir.shadow_failed")) detail = typeof p["reason_code"] === "string" ? p["reason_code"] : null;
    return {
      sequence: e.sequence,
      type,
      labelKey: supported ? type === "outcome.reported" ? `outcome.${String(p["status"] ?? "UNKNOWN")}` : `event.${type}` : "event.unsupported",
      occurredAt: e.occurred_at,
      supported,
      detail,
      ...(transition ? { transition } : {}),
    };
  });
}

export const TERMINAL_STATES: ReadonlySet<string> = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const RUN_STATES = new Set(["CREATED", "RUNNING", "WAITING_INPUT", "WAITING_APPROVAL", "VERIFYING", "NEEDS_RECONCILIATION", ...TERMINAL_STATES]);

export interface ConversationItem {
  id: string;
  role: "user" | "agent";
  text: string;
  pending: boolean;
  /** "reply" is a conversational turn the kernel did not verify (ADR 0022); old rows have no kind. */
  kind: "reply" | "message";
  /** True on the first reply of the thread (one run for now); later replies show the label only as a description. */
  firstReply: boolean;
}

export function selectConversation(view: RunView): ConversationItem[] {
  let seenReply = false;
  return view.events.flatMap(e => {
    if (e.schema_version !== "1") return [];
    const p = e.payload ?? {};
    const text = e.type === "input.requested" ? p["question"] : e.type === "input.received" ? p["input"] : e.type === "message.final" ? p["text"] : null;
    if (typeof text !== "string") return [];
    const kind = e.type === "input.requested" && p["kind"] === "reply" ? "reply" as const : "message" as const;
    const firstReply = kind === "reply" && !seenReply;
    if (kind === "reply") seenReply = true;
    return [{ id: e.event_id, role: e.type === "input.received" ? "user" as const : "agent" as const, text, pending: e.type === "input.requested" && text === view.question, kind, firstReply }];
  });
}

/** What a thread is built from: the server's conversation snapshot and its runs' events. */
export interface ThreadSource {
  snapshot: ConversationSnapshot | null;
  /** Event views of the thread's runs other than the active one, keyed by run id. */
  runs: Readonly<Record<string, RunView>>;
}

/** One run of a conversation thread, with its messages, as the server recorded them. */
export interface ThreadRunEntry {
  runId: string;
  /** The message that started the run, as the server stored it. */
  task: string;
  state: RunRecord["state"];
  reasonCode: RunRecord["reason_code"] | null;
  /** The revision shown with the run; an answer's `reply_to` carries it. */
  revision: number;
  createdAt: string;
  /** The conversation's latest run: the one a new message goes to. */
  latest: boolean;
  /** False when the run's events could not be read yet: its messages are unknown, not none. */
  loaded: boolean;
  messages: ConversationItem[];
}

/**
 * The conversation thread (ADR 0023, ADR 0034): the snapshot's runs, oldest first, each with
 * the messages of its own events. The active run's view is the controller's `view`, so a
 * thread never holds a second copy of it, and a sent message appears only once the server's
 * snapshot or events have it (AG-FE-2, EA-1). The reply label goes on the first reply of the
 * whole conversation (4b.2, extended to a thread).
 */
export function selectThread(source: ThreadSource, active: { runId: string | null; view: RunView }): ThreadRunEntry[] {
  const runs = source.snapshot?.runs ?? [];
  let seenReply = false;
  return runs.map((row, index) => {
    const live = active.runId === row.run_id && active.view.run?.run_id === row.run_id ? active.view : null;
    const view = live ?? source.runs[row.run_id] ?? null;
    const messages = (view ? selectConversation(view) : []).map(message => {
      const firstReply = message.kind === "reply" && !seenReply;
      if (message.kind === "reply") seenReply = true;
      return { ...message, firstReply };
    });
    const run = live?.run ?? null;
    return {
      runId: row.run_id,
      task: row.task,
      state: run?.state ?? row.state,
      reasonCode: (run ? run.reason_code : row.reason_code) ?? null,
      revision: run?.revision ?? row.revision,
      createdAt: row.created_at,
      latest: index === runs.length - 1,
      loaded: view !== null,
      messages,
    };
  });
}

/** True while the run waits on a conversational reply (not a clarification question). */
export function selectPendingReply(view: RunView): boolean {
  return view.run?.state === "WAITING_INPUT" && selectConversation(view).some(m => m.pending && m.kind === "reply");
}

/** Correlate host verification with the exact action; model prose supplies no fields. */
export function selectVerifiedResults(view: RunView): { actionId: string; fields: Record<string, unknown>; externalRefs: string[] }[] {
  return view.actions.flatMap(action => {
    if (action.state !== "VERIFIED") return [];
    const verified = view.events.some(e => e.schema_version === "1" && e.type === "outcome.reported" && e.payload?.["action_id"] === action.action_id && e.payload["status"] === "VERIFIED");
    if (!verified) return [];
    const refs = view.events.filter(e => e.schema_version === "1" && e.type === "action.receipt_recorded" && e.payload?.["action_id"] === action.action_id && e.payload["status"] === "COMMITTED").flatMap(e => {
      const refs = e.payload?.["external_refs"];
      return Array.isArray(refs) ? refs.filter((r): r is string => typeof r === "string") : [];
    });
    return [{ actionId: action.action_id, fields: action.arguments, externalRefs: [...new Set(refs)] }];
  });
}
