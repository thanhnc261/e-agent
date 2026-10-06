import type { ApprovalPresentation, RunEvent, RunSnapshot } from "@e-agent/client";
import { digest } from "../src/digest.ts";

export function ev(sequence: number, type: string, payload: Record<string, unknown> = {}): RunEvent {
  return {
    event_id: `evt-${sequence}`,
    tenant_id: "t",
    run_id: "run-1",
    sequence,
    type: type as RunEvent["type"],
    occurred_at: "2026-10-06T00:00:00Z",
    payload,
    schema_version: "1",
  };
}

export async function presentation(
  overrides: Partial<ApprovalPresentation> = {},
  quantity = "40",
): Promise<ApprovalPresentation> {
  const canonical = { arguments: { quantity } };
  return {
    run_id: "run-1",
    action_id: "act-1",
    run_revision: 5,
    digest: await digest(canonical),
    expires_at: new Date(Date.now() + 600_000).toISOString(),
    contract_id: "procurement.purchase_order.create_draft",
    binding_id: "b",
    connection_id: "c",
    credential_subject: "c@1/svc",
    canonical_proposal: canonical,
    material_fields: [{ path: "quantity", value: quantity, changed: false }],
    findings: [],
    ...overrides,
  };
}

export function snapshot(state: string, pending: ApprovalPresentation | null, latest = 0): RunSnapshot {
  return {
    run: {
      run_id: "run-1",
      tenant_id: "t",
      requester_id: "u",
      task: "restock",
      state: state as RunSnapshot["run"]["state"],
      revision: 5,
      logical_operation_id: "op",
      created_at: "2026-10-06T00:00:00Z",
    },
    latest_sequence: latest,
    actions: [],
    pending_approval: pending,
  };
}
