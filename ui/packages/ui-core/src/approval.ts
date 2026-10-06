/**
 * Approval state machine (UI architecture §4.3). Pure: the controller feeds it
 * events and the UI renders from its state. Approve is reachable only through an
 * explicit reviewing -> confirming -> submitting sequence.
 */
import type { ApprovalPresentation, Decision } from "@e-agent/client";

export type ApprovalPhase =
  | "idle"
  | "reviewing"
  | "confirming"
  | "submitting"
  | "approved"
  | "rejected"
  | "stale"
  | "expired"
  | "error";

export interface ApprovalState {
  phase: ApprovalPhase;
  presentation: ApprovalPresentation | null;
  /** Result of recomputing the digest locally; null while unchecked. */
  digestOk: boolean | null;
  /** Presentation that replaced the reviewed one (phase "stale"). */
  replacement: ApprovalPresentation | null;
  error: string | null;
}

export type ApprovalEvent =
  | { type: "PRESENTED"; presentation: ApprovalPresentation; digestOk: boolean }
  | { type: "CLEARED" }
  | { type: "REQUEST_CONFIRM" }
  | { type: "BACK" }
  | { type: "SUBMIT"; decision: Decision }
  | { type: "SUBMITTED"; decision: Decision }
  | { type: "FAILED"; error: string; stale: boolean }
  | { type: "EXPIRED" }
  | { type: "REVIEW_AGAIN" };

export const initialApproval: ApprovalState = {
  phase: "idle",
  presentation: null,
  digestOk: null,
  replacement: null,
  error: null,
};

function sameProposal(a: ApprovalPresentation, b: ApprovalPresentation): boolean {
  return a.action_id === b.action_id && a.digest === b.digest && a.run_revision === b.run_revision;
}

export function isExpired(p: ApprovalPresentation, now: number = Date.now()): boolean {
  return Date.parse(p.expires_at) <= now;
}

export function reduceApproval(state: ApprovalState, event: ApprovalEvent): ApprovalState {
  switch (event.type) {
    case "PRESENTED": {
      const current = state.presentation;
      if (current && sameProposal(current, event.presentation)) {
        return state.digestOk === event.digestOk ? state : { ...state, digestOk: event.digestOk };
      }
      if (current && (state.phase === "reviewing" || state.phase === "confirming")) {
        // A new revision or digest while the user is looking: force re-review.
        return { ...state, phase: "stale", replacement: event.presentation, error: null, digestOk: event.digestOk };
      }
      return { phase: "reviewing", presentation: event.presentation, digestOk: event.digestOk, replacement: null, error: null };
    }
    case "REVIEW_AGAIN":
      if (state.phase !== "stale" || !state.replacement) return state;
      return { ...state, phase: "reviewing", presentation: state.replacement, replacement: null };
    case "CLEARED":
      if (state.phase === "submitting" || state.phase === "approved" || state.phase === "rejected") return state;
      return initialApproval;
    case "REQUEST_CONFIRM":
      return state.phase === "reviewing" && canRequestApprove(state) ? { ...state, phase: "confirming" } : state;
    case "BACK":
      return state.phase === "confirming" ? { ...state, phase: "reviewing" } : state;
    case "SUBMIT":
      if (event.decision === "approved" && !(state.phase === "confirming" && canRequestApprove(state))) return state;
      if (event.decision === "rejected" && state.phase !== "reviewing" && state.phase !== "confirming") return state;
      return { ...state, phase: "submitting" };
    case "SUBMITTED":
      return { ...state, phase: event.decision === "approved" ? "approved" : "rejected" };
    case "FAILED":
      return { ...state, phase: event.stale ? "stale" : "error", error: event.error };
    case "EXPIRED":
      return state.phase === "approved" || state.phase === "rejected" ? state : { ...state, phase: "expired" };
  }
}

/** Guard used by every UI: Approve may be offered only when all of these hold. */
export function canRequestApprove(state: ApprovalState, now: number = Date.now()): boolean {
  const p = state.presentation;
  return p !== null && state.digestOk === true && !isExpired(p, now) && state.phase !== "stale";
}
