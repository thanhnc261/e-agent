/**
 * Citations and the explanation of one run, from its evidence bundle (ADR 0033 §6, ADR 0034
 * §3, §4). Pure, and read from that one server document only:
 *
 * - the explanation is the bundle's `explanation` key, in the server's order (goal, source
 *   facts, rules, proposals, rationale refs, approvals, receipts, outcomes), each value with
 *   the server's label. An unknown label is `unsupported`, never guessed (EA-8, AG-FE-13);
 * - citations come from `grounded_answer.citations` and, only in a run whose bundle reports
 *   `modes.grounded_answers: on`, from the `citations` of its `proposal.created` events.
 *   `shadow` citations were recorded for comparison and may not have resolved: never shown;
 * - a citation's record is its evidence id with the contract and revision of that source in
 *   `explanation.sources`; its field is the pointer. Its value is read only from the run's
 *   `actions[].approved_facts`, the fact with that evidence id, at the pointer (RFC 6901).
 *   Never from model text or the citation, which holds only a digest. Absent: `not_recorded`;
 * - a citation stored only as digests named nothing in the run: `unresolved`, with no id,
 *   pointer or digest carried forward, so no view can show it as a fact;
 * - model-authored text (the grounded summary) keeps its label and is rendered after facts.
 */
import { EVIDENCE_SCHEMA } from "./evidence.ts";

/** Labels the server gives explained values (`contracts/explain.py` ValueLabel), plus the
 * grounded section's own two (`kernel/evidence.py`). */
export const VALUE_LABELS = [
  "provider_read",
  "model_proposal",
  "approver_decision",
  "provider_receipt",
  "verified_outcome",
  "not_verified",
  "model_authored",
  "grounded_answer",
  "grounded",
  "unverified",
] as const;
export type ValueLabel = (typeof VALUE_LABELS)[number] | "unsupported";

export const EXPLANATION_COMPLETENESS = ["known", "partial", "unknown"] as const;
export type ExplanationCompleteness = (typeof EXPLANATION_COMPLETENESS)[number];

/** A cited value: what the run's approved fact holds at the pointer, or not recorded. */
export type CitedValue = { kind: "recorded"; value: unknown; key: string | null } | { kind: "not_recorded" };

export type CitationView =
  | {
      kind: "named";
      evidenceId: string;
      pointer: string;
      /** From `explanation.sources`; null when the explanation does not name that source. */
      contractId: string | null;
      revision: string | null;
      value: CitedValue;
      /** The server's label for this citation; null where it gives none (a typed answer's). */
      label: ValueLabel | null;
    }
  | { kind: "unresolved" };

export interface CitationGroup {
  origin: "grounded_answer" | "typed_answer";
  /** The answer contract the citations belong to; null when not recorded. */
  contractId: string | null;
  citations: CitationView[];
}

export interface AgentText {
  text: string;
  label: ValueLabel;
}

export interface SourceFactView {
  evidenceId: string;
  contractId: string | null;
  revision: string | null;
  label: ValueLabel;
}

export interface RuleView {
  ruleId: string;
  ruleVersion: string | null;
  status: string | null;
}

export interface RationaleView {
  stepId: string | null;
  goalRef: string | null;
  citedEvidence: string[];
  rulesConsidered: string[];
  /** Refs the kernel did not resolve, stored only as digests: counted, never named. */
  unresolvedRefs: number;
  summaryDigest: string | null;
  label: ValueLabel;
}

export interface ProposalView {
  actionId: string | null;
  contractId: string | null;
  state: string | null;
  digest: string | null;
  evidenceIds: string[] | null;
  label: ValueLabel;
  rationales: RationaleView[];
}

export interface ApprovalView {
  decision: string | null;
  actorId: string | null;
  policyVersion: string | null;
  label: ValueLabel;
}

export interface ReceiptView {
  status: string | null;
  externalRefs: string[] | null;
  label: ValueLabel;
}

export interface OutcomeRefView {
  actionId: string | null;
  status: string | null;
  label: ValueLabel;
}

export interface ExplanationBody {
  completeness: ExplanationCompleteness;
  goal: string | null;
  sources: SourceFactView[];
  rules: RuleView[];
  proposals: ProposalView[];
  approvals: ApprovalView[];
  receipts: ReceiptView[];
  outcomes: OutcomeRefView[];
}

export type ExplanationView =
  | { kind: "absent" }
  | { kind: "unsupported"; schema: string | null }
  | {
      kind: "ready";
      /** The run revision the bundle was read at; null when it does not say. */
      revision: number | null;
      /** Null when the bundle holds no `explanation` key (a server before ADR 0033 §6). */
      explanation: ExplanationBody | null;
      citations: CitationGroup[];
      /** Model-authored text, shown after the facts with its label. */
      agentText: AgentText | null;
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

function strings(value: unknown): string[] {
  return list(value).filter((v): v is string => typeof v === "string");
}

function label(value: unknown): ValueLabel {
  return (VALUE_LABELS as readonly string[]).includes(String(value)) ? (value as ValueLabel) : "unsupported";
}

const NOTHING = Symbol("nothing");

/**
 * The value at an RFC 6901 pointer, or `NOTHING` when the pointer names nothing (which is not
 * the same as a recorded JSON null).
 */
function resolvePointer(data: unknown, pointer: string): unknown {
  if (pointer === "") return data;
  if (!pointer.startsWith("/")) return NOTHING;
  let current: unknown = data;
  for (const raw of pointer.slice(1).split("/")) {
    const token = raw.replace(/~1/g, "/").replace(/~0/g, "~");
    if (Array.isArray(current)) {
      if (!/^(0|[1-9][0-9]*)$/.test(token) || Number(token) >= current.length) return NOTHING;
      current = current[Number(token)];
    } else if (current && typeof current === "object" && Object.hasOwn(current, token)) {
      current = (current as Record<string, unknown>)[token];
    } else return NOTHING;
  }
  return current;
}

function lastKey(pointer: string): string | null {
  const last = pointer.split("/").at(-1);
  return last ? last.replace(/~1/g, "/").replace(/~0/g, "~") : null;
}

/** Approved facts by evidence id, first occurrence first, from every action of the run. */
function approvedFacts(bundle: Record<string, unknown>): Map<string, unknown[]> {
  const facts = new Map<string, unknown[]>();
  for (const action of list(bundle["actions"])) {
    for (const fact of list(record(action)["approved_facts"])) {
      const f = record(fact);
      const id = text(record(f["evidence"])["evidence_id"]);
      if (!id) continue;
      facts.set(id, [...(facts.get(id) ?? []), f["data"]]);
    }
  }
  return facts;
}

function citedValue(facts: Map<string, unknown[]>, evidenceId: string, pointer: string): CitedValue {
  for (const data of facts.get(evidenceId) ?? []) {
    const value = resolvePointer(data, pointer);
    if (value !== NOTHING) return { kind: "recorded", value, key: lastKey(pointer) };
  }
  return { kind: "not_recorded" };
}

function citation(
  raw: unknown,
  sources: Map<string, SourceFactView>,
  facts: Map<string, unknown[]>,
  withLabel: boolean,
): CitationView {
  const c = record(raw);
  const evidenceId = text(c["evidence_id"]);
  const pointer = typeof c["pointer"] === "string" ? c["pointer"] : null;
  // Digest-only, or any shape without both refs as written: it named nothing in the run.
  if (!evidenceId || pointer === null) return { kind: "unresolved" };
  const source = sources.get(evidenceId);
  return {
    kind: "named",
    evidenceId,
    pointer,
    contractId: source?.contractId ?? null,
    revision: source?.revision ?? null,
    value: citedValue(facts, evidenceId, pointer),
    label: withLabel ? label(c["label"]) : null,
  };
}

function explanationBody(raw: Record<string, unknown>): ExplanationBody {
  const run = record(raw["run"]);
  const validation = record(raw["validation"]);
  const completeness = String(raw["completeness"]);
  return {
    completeness: (EXPLANATION_COMPLETENESS as readonly string[]).includes(completeness)
      ? (completeness as ExplanationCompleteness)
      : "unknown",
    goal: text(run["goal"]),
    sources: list(raw["sources"]).flatMap(s => {
      const f = record(s);
      const evidenceId = text(f["evidence_id"]);
      return evidenceId
        ? [
            {
              evidenceId,
              contractId: text(f["contract_id"]),
              revision: text(f["revision"]),
              label: label(f["label"]),
            },
          ]
        : [];
    }),
    rules: list(validation["rules_evaluated"]).flatMap(r => {
      const rule = record(r);
      const ruleId = text(rule["rule_id"]);
      return ruleId
        ? [{ ruleId, ruleVersion: text(rule["rule_version"]), status: text(rule["status"]) }]
        : [];
    }),
    proposals: list(raw["proposals"]).map(p => {
      const proposal = record(p);
      return {
        actionId: text(proposal["action_id"]),
        contractId: text(proposal["contract_id"]),
        state: text(proposal["state"]),
        digest: text(proposal["digest"]),
        evidenceIds: Array.isArray(proposal["evidence_ids"]) ? strings(proposal["evidence_ids"]) : null,
        label: label(proposal["label"]),
        rationales: list(proposal["rationales"]).map(r => {
          const rationale = record(r);
          return {
            stepId: text(rationale["step_id"]),
            goalRef: text(rationale["goal_ref"]),
            citedEvidence: strings(rationale["cited_evidence"]),
            rulesConsidered: strings(rationale["rules_considered"]),
            unresolvedRefs:
              list(rationale["unresolved_evidence_digests"]).length +
              list(rationale["unresolved_rule_digests"]).length +
              (rationale["goal_ref_digest"] ? 1 : 0),
            summaryDigest: text(rationale["summary_digest"]),
            label: label(rationale["label"]),
          };
        }),
      };
    }),
    approvals: list(raw["approvals"]).map(a => {
      const approval = record(a);
      return {
        decision: text(approval["decision"]),
        actorId: text(approval["actor_id"]),
        policyVersion: text(approval["policy_version"]),
        label: label(approval["label"]),
      };
    }),
    receipts: list(raw["receipts"]).map(r => {
      const receipt = record(r);
      return {
        status: text(receipt["status"]),
        externalRefs: Array.isArray(receipt["external_refs"]) ? strings(receipt["external_refs"]) : null,
        label: label(receipt["label"]),
      };
    }),
    outcomes: list(raw["outcomes"]).map(o => {
      const outcome = record(o);
      return {
        actionId: text(outcome["action_id"]),
        status: text(outcome["status"]),
        label: label(outcome["label"]),
      };
    }),
  };
}

/** Normalise a run's evidence bundle into its explanation and citations. */
export function selectExplanation(bundle: Record<string, unknown> | null | undefined): ExplanationView {
  if (!bundle) return { kind: "absent" };
  const schema = text(bundle["schema"]);
  if (schema !== EVIDENCE_SCHEMA) return { kind: "unsupported", schema };
  const rawExplanation = bundle["explanation"];
  const explanation =
    rawExplanation && typeof rawExplanation === "object" && !Array.isArray(rawExplanation)
      ? explanationBody(rawExplanation as Record<string, unknown>)
      : null;
  const sources = new Map((explanation?.sources ?? []).map(s => [s.evidenceId, s]));
  const facts = approvedFacts(bundle);
  const citations: CitationGroup[] = [];
  let agentText: AgentText | null = null;

  const grounded = bundle["grounded_answer"];
  if (grounded && typeof grounded === "object") {
    const g = record(grounded);
    const items = list(g["citations"]).map(c => citation(c, sources, facts, true));
    if (items.length)
      citations.push({ origin: "grounded_answer", contractId: text(g["contract_id"]), citations: items });
    const summary = record(g["summary"]);
    const summaryText = text(summary["text"]);
    if (summaryText) agentText = { text: summaryText, label: label(summary["label"]) };
  }

  if (record(bundle["modes"])["grounded_answers"] === "on") {
    for (const e of list(bundle["events"])) {
      const ev = record(e);
      if (ev["schema_version"] !== "1" || ev["type"] !== "proposal.created") continue;
      const payload = record(ev["payload"]);
      const items = list(payload["citations"]).map(c => citation(c, sources, facts, false));
      if (items.length)
        citations.push({
          origin: "typed_answer",
          contractId: text(payload["contract_id"]),
          citations: items,
        });
    }
  }

  const revision = record(bundle["run"])["revision"];
  return {
    kind: "ready",
    revision: typeof revision === "number" ? revision : null,
    explanation,
    citations,
    agentText,
  };
}
