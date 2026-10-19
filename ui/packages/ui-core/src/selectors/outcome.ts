/**
 * Typed projection of a run's result.
 *
 * Committed, verified, failed and unknown are kept distinct. A check whose payload
 * does not state `passed` is reported as `null` (unknown) and must never be shown
 * as a failure or as a pass, and `NEEDS_RECONCILIATION` stays unresolved until the
 * server says otherwise — the browser never promotes a result. A run the server ended
 * with reason code `grounded` (ADR 0033 §3: its citations resolved against the run's own
 * evidence, no independent read-back) is `grounded`, never `verified` (PR-19).
 */
import { statusKey } from "../presentation.ts";
import { selectVerifiedResults, type RunView } from "../store.ts";

export const RESULT_STATES = [
  "VERIFYING",
  "NEEDS_RECONCILIATION",
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
] as const;

export type OutcomeStatus =
  | "none"
  | "checking"
  | "unresolved"
  | "verified"
  | "grounded"
  | "failed"
  | "cancelled";

export interface OutcomeCheck {
  name: string;
  /** `null` means the host did not record a verdict; it is not a failure. */
  passed: boolean | null;
  observed: string | null;
}

export interface OutcomeAction {
  actionId: string;
  contractId: string;
  state: string;
}

export interface OutcomeView {
  state: string | null;
  status: OutcomeStatus;
  /** The run's reason code as the server sent it; `null` when it sent none. */
  reasonCode: string | null;
  /** The i18n key of the result label: a grounded end has its own, never the verified one. */
  labelKey: string;
  /** True while an external effect may have happened without a confirmed result. */
  unresolved: boolean;
  reason: string | null;
  verified: ReturnType<typeof selectVerifiedResults>;
  checks: OutcomeCheck[];
  actions: OutcomeAction[];
}

const STATUS: Record<string, OutcomeStatus> = {
  VERIFYING: "checking",
  NEEDS_RECONCILIATION: "unresolved",
  SUCCEEDED: "verified",
  FAILED: "failed",
  CANCELLED: "cancelled",
};

function verdict(value: unknown): boolean | null {
  return value === true ? true : value === false ? false : null;
}

export function selectOutcome(view: RunView): OutcomeView {
  const run = view.run;
  const state = run?.state ?? null;
  const reasonCode = run?.reason_code ?? null;
  const grounded = state === "SUCCEEDED" && reasonCode === "grounded";
  const status = grounded ? "grounded" : ((state && STATUS[state]) ?? "none");
  const report = view.events
    .filter(e => e.schema_version === "1" && e.type === "outcome.reported")
    .at(-1)?.payload;
  const rawChecks = Array.isArray(report?.["checks"]) ? (report["checks"] as unknown[]) : [];
  return {
    state,
    status,
    reasonCode,
    labelKey: grounded ? "status.SUCCEEDED.grounded" : statusKey(state ?? undefined),
    unresolved: state === "NEEDS_RECONCILIATION",
    reason: run?.reason ?? null,
    verified: selectVerifiedResults(view),
    checks: rawChecks.map(raw => {
      const c = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
      return {
        name: typeof c["name"] === "string" ? c["name"] : "",
        passed: verdict(c["passed"]),
        observed: typeof c["observed"] === "string" && c["observed"] ? c["observed"] : null,
      };
    }),
    actions: view.actions.map(a => ({ actionId: a.action_id, contractId: a.contract_id, state: a.state })),
  };
}

export function hasResult(state: string | null | undefined): boolean {
  return (RESULT_STATES as readonly string[]).includes(state ?? "");
}
