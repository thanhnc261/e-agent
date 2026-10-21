/**
 * Pure helpers for the conversation thread (ADR 0034 §2, owner-selected mockup A1). Each
 * reads only server fields: the features read, run states and recorded events.
 */
import { selectViewMode, type ControllerState, type FeaturesState } from "../controller.ts";
import { runStatusKey } from "../presentation.ts";
import {
  selectPendingReply,
  selectTimeline,
  TERMINAL_STATES,
  type RunView,
  type ThreadRunEntry,
  type TimelineItem,
} from "../store.ts";

/**
 * True when the server reports `conversations: on`. The composer then keeps no local lock:
 * a message that cannot go now is refused by the server with its hint, and the draft is
 * kept (G-B 4). It is the controller's own rule, so the input never disagrees with `start()`.
 */
export function isConversationsOn(features: FeaturesState): boolean {
  return features.kind === "ready" && features.conversations === "on";
}

/**
 * True when a UI shows the thread: `selectViewMode` says so, and the attached run is not a
 * legacy run outside every conversation (that one keeps the per-run view, G-B 2).
 */
export function selectThreadShown(
  state: Pick<ControllerState, "features" | "threads" | "thread" | "runId" | "conversationId">,
): boolean {
  return selectViewMode(state).kind === "thread" && !(state.runId && !state.conversationId);
}

/**
 * The stop slot under the composer (4e.2 stop ruling, AG-CTRL-1, EA-4):
 * - `active`: the latest run can be stopped;
 * - `idle`: nothing is running, so Stop stays in place, disabled, with its reason;
 * - `unconfirmed`: the result may have happened, so Stop is disabled and the safe status
 *   check is offered instead.
 */
export type StopControl = { kind: "active" } | { kind: "idle" } | { kind: "unconfirmed" };

export function selectStopControl(state: string | null | undefined): StopControl {
  if (state === "NEEDS_RECONCILIATION") return { kind: "unconfirmed" };
  if (!state || TERMINAL_STATES.has(state)) return { kind: "idle" };
  return { kind: "active" };
}

/** True when the entry is the attached run, whose live view (actions, approval) is known. */
export function isLiveEntry(entry: ThreadRunEntry, active: { runId: string | null; view: RunView }): boolean {
  return entry.runId === active.runId && active.view.run?.run_id === entry.runId;
}

/**
 * A thread run's status label: the live run's from its actions and pending reply, any other
 * run's from the snapshot row. Server fields only, so grounded is never shown as verified.
 */
export function threadRunStatusKey(
  entry: ThreadRunEntry,
  active: { runId: string | null; view: RunView },
): string {
  const run = active.view.run;
  if (run && isLiveEntry(entry, active))
    return runStatusKey(run.state, active.view.actions, selectPendingReply(active.view), run.reason_code);
  return runStatusKey(entry.state, [], false, entry.reasonCode);
}

const LINE_SKIPPED: ReadonlySet<string> = new Set(["run.state_changed", "run.terminal"]);

/**
 * The run card's one result line, from the run's recorded events only (EA-5): its latest
 * outcome when one was reported, otherwise its latest recorded event. State changes are
 * left out because the card's badge already says the state. Null when nothing is recorded.
 */
export function selectRunLine(view: RunView | null): TimelineItem | null {
  if (!view) return null;
  const items = selectTimeline(view).filter(item => item.supported && !LINE_SKIPPED.has(item.type));
  return items.filter(item => item.type === "outcome.reported").at(-1) ?? items.at(-1) ?? null;
}

/**
 * The connections the server recorded on this run's reads (`read.recorded`), in order, without
 * repeats (gap audit F-11, AG-ID-5). Ids only, as recorded; never a value from model text.
 */
export function selectReadConnections(view: RunView | null): string[] {
  if (!view) return [];
  const ids = view.events.flatMap(event => {
    const id =
      event.schema_version === "1" && event.type === "read.recorded"
        ? event.payload?.["connection_id"]
        : null;
    return typeof id === "string" && id ? [id] : [];
  });
  return [...new Set(ids)];
}
