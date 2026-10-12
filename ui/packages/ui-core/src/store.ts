/**
 * Event-sourced run view (UI architecture §3 L3). The server snapshot is the base;
 * events are ordered deltas deduplicated by ``sequence``. A gap or an unknown event
 * type never guesses: it asks the controller for a fresh snapshot.
 */
import type { ActionSummary, RunEvent, RunRecord, RunSnapshot, TextFrame } from "@e-agent/client";

export const KNOWN_EVENT_TYPES: ReadonlySet<string> = new Set([
  "run.created",
  "run.state_changed",
  "read.recorded",
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
  }
  if (type === "message.final" && typeof payload["text"] === "string") {
    next.finalMessage = payload["text"];
    next.streamingText = "";
  }
  if (type === "input.requested" && typeof payload["question"] === "string") next.question = payload["question"];
  if (type === "input.received") next.question = null;
  if (SNAPSHOT_TRIGGERS.has(type)) next.needsSnapshot = true;
  return next;
}

export function reduceRunView(view: RunView, action: RunViewAction): RunView {
  switch (action.type) {
    case "reset":
      return emptyRunView;
    case "text": {
      if (TERMINAL_STATES.has(view.run?.state ?? "")) return view;
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
        streamingText: TERMINAL_STATES.has(action.snapshot.run.state) ? "" : view.streamingText,
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
  /** For a run state change: the server's states, so a UI can label them. */
  transition?: { from: string; to: string };
}

/** Plain-data timeline; detail is a short, non-HTML string. */
export function selectTimeline(view: RunView): TimelineItem[] {
  return view.events.map((e) => {
    const type = e.type as string;
    const supported = e.schema_version === "1" && KNOWN_EVENT_TYPES.has(type);
    const p = e.payload ?? {};
    let detail: string | null = null;
    if (supported && type === "run.state_changed") detail = `${String(p["from"])} → ${String(p["to"])}`;
    else if (supported && (type === "validation.completed" || type === "outcome.reported")) detail = String(p["status"] ?? "");
    else if (supported && type === "approval.decided") detail = String(p["decision"] ?? "");
    else if (supported && (type === "proposal.created" || type === "read.recorded")) detail = String(p["contract_id"] ?? "");
    return {
      sequence: e.sequence,
      type,
      labelKey: supported ? type === "outcome.reported" ? `outcome.${String(p["status"] ?? "UNKNOWN")}` : `event.${type}` : "event.unsupported",
      occurredAt: e.occurred_at,
      supported,
      detail,
      ...(supported && type === "run.state_changed" ? { transition: { from: String(p["from"]), to: String(p["to"]) } } : {}),
    };
  });
}

export const TERMINAL_STATES: ReadonlySet<string> = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
const RUN_STATES = new Set(["CREATED", "RUNNING", "WAITING_INPUT", "WAITING_APPROVAL", "VERIFYING", "NEEDS_RECONCILIATION", ...TERMINAL_STATES]);

export function selectConversation(view: RunView): { id: string; role: "user" | "agent"; text: string; pending: boolean }[] {
  return view.events.flatMap(e => {
    if (e.schema_version !== "1") return [];
    const p = e.payload ?? {};
    const text = e.type === "input.requested" ? p["question"] : e.type === "input.received" ? p["input"] : e.type === "message.final" ? p["text"] : null;
    return typeof text === "string" ? [{ id: e.event_id, role: e.type === "input.received" ? "user" as const : "agent" as const, text, pending: e.type === "input.requested" && text === view.question }] : [];
  });
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
