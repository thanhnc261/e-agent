/** Maps a run state to a status tone. Presentation only; it decides nothing. */
import type { StatusTone } from "../../primitives/variants.ts";

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

export function runStateTone(state: string | undefined): StatusTone {
  return (state && TONES[state]) || "neutral";
}
