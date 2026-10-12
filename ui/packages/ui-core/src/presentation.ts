/** Generic host presentation helpers. Labels never change approved values. */
import type { ApprovalPresentation } from "@e-agent/client";

export function readableLabel(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[_.-]+/g, " ").replace(/\bv\d+\b/g, "").trim().replace(/^./, c => c.toUpperCase());
}

export function canonicalFields(argumentsValue: unknown, prefix = ""): Map<string, string> | null {
  if (!argumentsValue || typeof argumentsValue !== "object" || Array.isArray(argumentsValue)) return null;
  const fields = new Map<string, string>();
  for (const [key, value] of Object.entries(argumentsValue)) {
    const path = prefix + key;
    if (value !== null && typeof value === "object") {
      const nested = canonicalFields(value, path + ".");
      if (!nested) return null;
      for (const [p, v] of nested) { if (fields.has(p)) return null; fields.set(p, v); }
    } else {
      if (fields.has(path) || !["string", "boolean"].includes(typeof value) && value !== null) return null;
      fields.set(path, value === null ? "null" : typeof value === "boolean" ? value ? "True" : "False" : String(value));
    }
  }
  return fields;
}

/** Fail closed on a missing, substituted, extra or duplicate human-visible term. */
export function presentationMatchesCanonical(p: ApprovalPresentation): boolean {
  const fields = canonicalFields(p.canonical_proposal["arguments"]);
  if (!fields || fields.size !== p.material_fields.length) return false;
  const seen = new Set<string>();
  for (const f of p.material_fields) {
    if (seen.has(f.path) || fields.get(f.path) !== f.value) return false;
    seen.add(f.path);
  }
  for (const [key, expected] of [["contract_id", p.contract_id], ["connection_id", p.connection_id], ["binding_id", p.binding_id], ["credential_subject", p.credential_subject]] as const) {
    if (key in p.canonical_proposal && p.canonical_proposal[key] !== expected) return false;
  }
  const effects = p.canonical_proposal["expected_effects"];
  if (effects !== undefined && JSON.stringify(effects) !== JSON.stringify(p.expected_effects)) return false;
  return true;
}

export function statusKey(state: string | undefined): string {
  return `status.${state ?? "idle"}`;
}

const IN_FLIGHT = new Set(["RUNNING", "VERIFYING"]);

/**
 * Run-status label that keeps working, sending, recorded and unconfirmed apart.
 * While a run is in flight, an external change the server reports as being sent,
 * committed or unknown is named in its own words, read from the server's action
 * states only. The browser never infers or promotes a phase.
 */
export function runStatusKey(state: string | undefined, actions: readonly { state: string }[] = []): string {
  if (state && IN_FLIGHT.has(state)) {
    const states = new Set(actions.map(a => a.state));
    if (states.has("UNKNOWN")) return "status.phase.UNKNOWN";
    if (states.has("DISPATCHING")) return "status.phase.DISPATCHING";
    if (state === "RUNNING" && states.has("COMMITTED")) return "status.phase.COMMITTED";
  }
  return statusKey(state);
}

export function actionStatusKey(state: string): string {
  return `action.state.${state}`;
}

export function canCompose(state: string | undefined): boolean {
  return !state || ["WAITING_INPUT", "SUCCEEDED", "FAILED", "CANCELLED"].includes(state);
}
