/**
 * Discovery projections (ADR 0017) at the client/core boundary. Loading, empty,
 * denied and unsupported stay distinct, and no response is trusted to claim health.
 */
import { describe, expect, it } from "vitest";
import {
  DISCOVERY_SCHEMA_VERSION,
  projectConnections,
  projectTaskCatalog,
} from "../src/selectors/discovery.ts";

const envelope = { schema_version: DISCOVERY_SCHEMA_VERSION, observed_at: "2026-10-09T00:00:00Z" };

/** A complete schema-1 connection; overrides exercise one field at a time. */
function connectionEntry(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    connection_id: "conn-1",
    integration_id: "erp",
    ownership: "tenant_shared",
    acting_identity: "integration-user",
    allowed_resources: ["order"],
    capabilities: ["erp.order.create.v1"],
    configuration_status: "active",
    observed_health: "unknown",
    revision: 2,
    ...overrides,
  };
}

/** A complete schema-1 template. */
function templateEntry(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    template_id: "erp.order.create.v1",
    title: "order create (erp)",
    description: "d",
    input_intent: "free_text",
    availability: "available",
    unavailable_reason: null,
    required_capabilities: ["erp.order.create.v1"],
    bounded_context: "erp",
    ...overrides,
  };
}

describe("connection projection", () => {
  it("reports an unrecognised version as unsupported rather than rendering it", () => {
    expect(projectConnections({ schema_version: "99", connections: [{}] })).toEqual({
      kind: "unsupported",
      schemaVersion: "99",
    });
    expect(projectConnections(null)).toEqual({ kind: "unsupported", schemaVersion: null });
    expect(projectConnections({ connections: [] })).toEqual({
      kind: "unsupported",
      schemaVersion: null,
    });
  });

  it("distinguishes an empty inventory from a missing one", () => {
    expect(projectConnections({ ...envelope, connections: [] })).toEqual({
      kind: "ready",
      observedAt: "2026-10-09T00:00:00Z",
      items: [],
    });
  });

  it("keeps an undisclosed acting identity null and never asserts health", () => {
    const state = projectConnections({
      ...envelope,
      connections: [connectionEntry({ acting_identity: null, observed_health: "connected" })],
    });
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    const connection = state.items[0]!;
    expect(connection.actingIdentity).toBeNull();
    // A response claiming anything other than unknown health is not believed.
    expect(connection.observedHealth).toBe("unknown");
    expect(connection.unusable).toBe(false);
  });

  it("marks recorded states that cannot act, including revoked", () => {
    for (const status of ["revoked", "disabled", "reauth_required", "degraded", "draft"]) {
      const state = projectConnections({
        ...envelope,
        connections: [connectionEntry({ configuration_status: status })],
      });
      expect(state.kind === "ready" && state.items[0]!.unusable, status).toBe(true);
    }
  });

  it("reports an entry without a stable identity instead of dropping it", () => {
    const state = projectConnections({
      ...envelope,
      connections: [{ integration_id: "erp" }, { connection_id: "c" }, "nonsense"],
    });
    // Silently shortening the list would present a partial inventory as complete.
    expect(state.kind).toBe("malformed");
  });
});

describe("task catalog projection", () => {
  it("keeps a reason on every unavailable template and none on an available one", () => {
    const state = projectTaskCatalog({
      ...envelope,
      templates: [
        // An available template keeps no reason, even when the server sends one.
        templateEntry({ unavailable_reason: "no_usable_connection" }),
        templateEntry({
          template_id: "erp.other.create.v1",
          title: "",
          availability: "unavailable",
          unavailable_reason: null,
        }),
        templateEntry({ template_id: "erp.third.create.v1", availability: "something-new" }),
      ],
    });
    expect(state.kind).toBe("ready");
    if (state.kind !== "ready") return;
    expect(state.items[0]!.available).toBe(true);
    expect(state.items[0]!.unavailableReason).toBeNull();
    expect(state.items[1]!.unavailableReason).toBe("unknown");
    // An availability value this build does not recognise is never treated as usable.
    expect(state.items[2]!.available).toBe(false);
    // An empty title falls back to the identity instead of rendering nothing.
    expect(state.items[1]!.title).toBe("erp.other.create.v1");
  });
});

describe("a declared version must actually be honoured", () => {
  it("rejects a missing or wrongly-typed collection instead of reporting an empty one", () => {
    // Exactly the inputs the independent review reproduced.
    expect(projectConnections({ schema_version: "1" }).kind).toBe("malformed");
    expect(projectTaskCatalog({ schema_version: "1", templates: "invalid" }).kind).toBe("malformed");
    expect(projectConnections({ schema_version: "1", connections: {} }).kind).toBe("malformed");
    expect(projectTaskCatalog({ schema_version: "1" }).kind).toBe("malformed");
  });

  it("keeps malformed distinct from a legitimate empty list", () => {
    expect(projectConnections({ ...envelope, connections: [] })).toEqual({
      kind: "ready",
      observedAt: "2026-10-09T00:00:00Z",
      items: [],
    });
    expect(projectTaskCatalog({ ...envelope, templates: [] }).kind).toBe("ready");
  });

  it("keeps malformed distinct from unsupported and from denied", () => {
    // Unsupported is about the version; malformed is about the payload.
    expect(projectConnections({ schema_version: "99", connections: "x" })).toEqual({
      kind: "unsupported",
      schemaVersion: "99",
    });
    expect(projectConnections([]).kind).toBe("unsupported");
  });

  it("never invents a revision for a connection that omits one", () => {
    const partial = projectConnections({
      ...envelope,
      connections: [{ connection_id: "conn-1", integration_id: "erp" }],
    });
    // The review observed `revision: 0` and `unusable: false` for this input.
    expect(partial.kind).toBe("malformed");
    expect(JSON.stringify(partial)).not.toContain('"revision":0');
  });

  it.each([
    ["connection_id", ""],
    ["integration_id", 7],
    ["ownership", null],
    ["configuration_status", undefined],
    ["allowed_resources", "order"],
    ["capabilities", [1]],
    ["revision", "2"],
    ["revision", 1.5],
    ["acting_identity", 7],
  ])("rejects a connection whose %s is %j", (field, value) => {
    const state = projectConnections({ ...envelope, connections: [connectionEntry({ [field]: value })] });
    expect(state.kind).toBe("malformed");
  });

  it.each([
    ["template_id", ""],
    ["description", null],
    ["availability", 1],
    ["required_capabilities", "x"],
    ["bounded_context", 3],
  ])("rejects a template whose %s is %j", (field, value) => {
    const state = projectTaskCatalog({ ...envelope, templates: [templateEntry({ [field]: value })] });
    expect(state.kind).toBe("malformed");
  });

  it("still fails an unrecognised availability closed rather than rejecting the catalog", () => {
    // A value this build does not know is not usable; a wrong *type* is malformed.
    const state = projectTaskCatalog({
      ...envelope,
      templates: [templateEntry({ availability: "something-new" })],
    });
    expect(state.kind).toBe("ready");
    expect(state.kind === "ready" && state.items[0]!.available).toBe(false);
  });

  it("does not throw for any malformed input", () => {
    for (const body of [null, undefined, 0, "x", [], { schema_version: 1 }, { schema_version: "1", connections: [null] }]) {
      expect(() => projectConnections(body), JSON.stringify(body)).not.toThrow();
      expect(() => projectTaskCatalog(body), JSON.stringify(body)).not.toThrow();
    }
  });
});
