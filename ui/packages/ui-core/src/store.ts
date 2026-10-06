/**
 * Event-sourced run view (UI architecture §3 L3). The server snapshot is the base;
 * events are ordered deltas deduplicated by ``sequence``. A gap or an unknown event
 * type never guesses: it asks the controller for a fresh snapshot.
 */
import type { ActionSummary, RunEvent, RunRecord, RunSnapshot } from "@e-agent/client";

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
]);

export interface RunView {
  run: RunRecord | null;
  events: RunEvent[];
  lastSequence: number;
  actions: ActionSummary[];
  finalMessage: string | null;
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
  needsSnapshot: false,
  unsupportedEvents: 0,
};

export type RunViewAction =
  | { type: "snapshot"; snapshot: RunSnapshot }
  | { type: "events"; events: RunEvent[] }
  | { type: "reset" };

function applyEvent(view: RunView, event: RunEvent): RunView {
  if (event.sequence <= view.lastSequence) return view; // duplicate (replay/reconnect)
  if (event.sequence !== view.lastSequence + 1) return { ...view, needsSnapshot: true }; // gap
  const next: RunView = { ...view, events: [...view.events, event], lastSequence: event.sequence };
  const type = event.type as string;
  if (!KNOWN_EVENT_TYPES.has(type)) {
    return { ...next, needsSnapshot: true, unsupportedEvents: view.unsupportedEvents + 1 };
  }
  const payload = event.payload ?? {};
  if (type === "run.state_changed" && next.run && typeof payload["to"] === "string") {
    next.run = { ...next.run, state: payload["to"] as RunRecord["state"] };
  }
  if (type === "message.final" && typeof payload["text"] === "string") {
    next.finalMessage = payload["text"];
  }
  if (SNAPSHOT_TRIGGERS.has(type)) next.needsSnapshot = true;
  return next;
}

export function reduceRunView(view: RunView, action: RunViewAction): RunView {
  switch (action.type) {
    case "reset":
      return emptyRunView;
    case "snapshot":
      return {
        ...view,
        run: action.snapshot.run,
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
}

/** Plain-data timeline; detail is a short, non-HTML string. */
export function selectTimeline(view: RunView): TimelineItem[] {
  return view.events.map((e) => {
    const type = e.type as string;
    const supported = KNOWN_EVENT_TYPES.has(type);
    const p = e.payload ?? {};
    let detail: string | null = null;
    if (type === "run.state_changed") detail = `${String(p["from"])} → ${String(p["to"])}`;
    else if (type === "validation.completed" || type === "outcome.reported") detail = String(p["status"] ?? "");
    else if (type === "approval.decided") detail = String(p["decision"] ?? "");
    else if (type === "proposal.created" || type === "read.recorded") detail = String(p["contract_id"] ?? "");
    return {
      sequence: e.sequence,
      type,
      labelKey: supported ? `event.${type}` : "event.unsupported",
      occurredAt: e.occurred_at,
      supported,
      detail,
    };
  });
}

export const TERMINAL_STATES: ReadonlySet<string> = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
