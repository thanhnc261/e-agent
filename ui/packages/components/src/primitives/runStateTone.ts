/** Maps a run state to a status tone. Presentation only; it decides nothing. */
import type { StatusTone } from "./variants.ts";

const TONES: Record<string, StatusTone> = {
  CREATED: "progress",
  RUNNING: "progress",
  VERIFYING: "progress",
  WAITING_INPUT: "attention",
  WAITING_APPROVAL: "attention",
  NEEDS_RECONCILIATION: "unknown",
  SUCCEEDED: "verified",
  FAILED: "failed",
  CANCELLED: "neutral",
};

/** A run the server ended `grounded` is never shown with the verified tone (PR-19). */
export function runStateTone(state: string | undefined, reasonCode?: string | null): StatusTone {
  if (state === "SUCCEEDED" && reasonCode === "grounded") return "neutral";
  return (state && TONES[state]) || "neutral";
}
