/**
 * Typed projection of the evidence bundle (`e-agent-evidence-v1`).
 *
 * The bundle is a server-owned JSON document, so it is validated here at the
 * boundary and views receive a discriminated union instead of parsing records in
 * JSX. A value the bundle does not carry stays `null`; it never becomes an empty
 * string, a zero or an assumed "complete". An unrecognised schema is reported as
 * unsupported rather than rendered on a best-effort basis.
 */

export const EVIDENCE_SCHEMA = "e-agent-evidence-v1";

export const COMPLETENESS = ["complete", "partial", "unknown"] as const;
export type Completeness = (typeof COMPLETENESS)[number];

export interface EvidenceDatum {
  path: string;
  /** Rendered form of an opaque domain value; objects are serialised, not dropped. */
  value: string;
}

export interface EvidenceSource {
  evidenceId: string;
  source: string | null;
  locator: string | null;
  revision: string | null;
  observedAt: string | null;
  scope: string | null;
  completeness: Completeness;
  environment: string | null;
  contractId: string | null;
  data: EvidenceDatum[];
}

export type EvidenceView =
  | { kind: "absent" }
  | { kind: "unsupported"; schema: string | null }
  | {
      kind: "ready";
      schema: string;
      generatedAt: string | null;
      environment: string | null;
      classification: string | null;
      rulesEvaluated: string[];
      sources: EvidenceSource[];
    };

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function completeness(value: unknown): Completeness {
  return (COMPLETENESS as readonly string[]).includes(String(value)) ? (value as Completeness) : "unknown";
}

function render(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function toSource(fact: unknown): EvidenceSource | null {
  const f = record(fact);
  const ref = record(f["evidence"]);
  const evidenceId = text(ref["evidence_id"]);
  if (!evidenceId) return null; // Without provenance identity it is not a source.
  return {
    evidenceId,
    source: text(ref["source"]),
    locator: text(ref["locator"]),
    revision: text(ref["revision"]),
    observedAt: text(ref["observed_at"]),
    scope: text(ref["scope"]),
    completeness: completeness(ref["completeness"]),
    environment: text(ref["environment"]),
    contractId: text(f["contract_id"]),
    data: Object.entries(record(f["data"])).map(([path, value]) => ({ path, value: render(value) })),
  };
}

/** Normalise the bundle. Repeated evidence ids collapse to their first occurrence. */
export function selectEvidence(bundle: Record<string, unknown> | null | undefined): EvidenceView {
  if (!bundle) return { kind: "absent" };
  const schema = text(bundle["schema"]);
  if (schema !== EVIDENCE_SCHEMA) return { kind: "unsupported", schema };
  const sources = new Map<string, EvidenceSource>();
  for (const action of list(bundle["actions"])) {
    for (const fact of list(record(action)["approved_facts"])) {
      const source = toSource(fact);
      if (source && !sources.has(source.evidenceId)) sources.set(source.evidenceId, source);
    }
  }
  return {
    kind: "ready",
    schema,
    generatedAt: text(bundle["generated_at"]),
    environment: text(bundle["environment"]),
    classification: text(bundle["classification"]),
    rulesEvaluated: list(bundle["rules_evaluated"]).filter((r): r is string => typeof r === "string"),
    sources: [...sources.values()],
  };
}
