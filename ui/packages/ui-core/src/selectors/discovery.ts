/**
 * Typed projections of the member discovery read models (ADR 0017).
 *
 * The browser validates the envelope it was given and maps it to a view model with
 * pure functions. Loading, empty, denied, unsupported, malformed and error are
 * distinct states: a missing response is never rendered as "no connections", a
 * denied one is never rendered as empty, an unrecognised `schema_version` is
 * reported rather than displayed, and a response that claims a version it does not
 * honour is reported as malformed rather than silently shortened into an
 * apparently complete inventory.
 *
 * These are display projections. They resolve no credential, choose no acting
 * identity and authorize nothing; the server re-authorizes every action.
 */
import type { MemberConnections, TaskCatalog } from "@e-agent/client";

export const DISCOVERY_SCHEMA_VERSION = "1";

export type DiscoveryState<T> =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; observedAt: string | null; items: T[] }
  /** The caller is authenticated but may not see this projection. */
  | { kind: "denied" }
  /** The server does not offer it, or offers a version this build cannot read. */
  | { kind: "unsupported"; schemaVersion: string | null }
  /** The version is one this build reads, but the payload does not honour it. */
  | { kind: "malformed"; detail: string }
  | { kind: "error"; message: string };

export interface ConnectionView {
  connectionId: string;
  integrationId: string;
  ownership: string;
  /** `null` when the connection does not publish a subject. Never a placeholder. */
  actingIdentity: string | null;
  allowedResources: string[];
  capabilities: string[];
  configurationStatus: string;
  /** Always unknown today: no provider was contacted to produce this view. */
  observedHealth: "unknown";
  revision: number;
  /** True when the recorded configuration state means the connection cannot act. */
  unusable: boolean;
}

export interface TaskTemplateView {
  templateId: string;
  title: string;
  description: string;
  available: boolean;
  /** Bounded machine reason; the UI maps it to a message it owns. */
  unavailableReason: string | null;
  requiredCapabilities: string[];
  boundedContext: string;
}

/** Recorded states in which a connection cannot currently act. */
const UNUSABLE_STATUSES = new Set(["revoked", "disabled", "reauth_required", "degraded", "draft"]);

class MalformedResponse extends Error {}

function fail(detail: string): never {
  throw new MalformedResponse(detail);
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

/** A required string. Present and of the right type, though it may be empty. */
function required(entry: Record<string, unknown>, key: string): string {
  const value = entry[key];
  if (typeof value !== "string") fail(`${key} must be a string`);
  return value as string;
}

/** A required string that must also identify something. */
function identity(entry: Record<string, unknown>, key: string): string {
  const value = required(entry, key);
  if (value.length === 0) fail(`${key} must not be empty`);
  return value;
}

function nullableText(entry: Record<string, unknown>, key: string): string | null {
  const value = entry[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") fail(`${key} must be a string or null`);
  return value.length > 0 ? value : null;
}

function stringList(entry: Record<string, unknown>, key: string): string[] {
  const value = entry[key];
  if (!Array.isArray(value)) fail(`${key} must be an array`);
  if (value.some(item => typeof item !== "string")) fail(`${key} must contain strings`);
  return value as string[];
}

function integer(entry: Record<string, unknown>, key: string): number {
  const value = entry[key];
  if (typeof value !== "number" || !Number.isInteger(value)) fail(`${key} must be an integer`);
  return value as number;
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * Validate the envelope and the collection together. A declared version this build
 * reads must come with the collection that version defines: a missing or
 * wrongly-typed collection is malformed, not an empty inventory.
 */
function collection(
  body: unknown,
  key: string,
): { observedAt: string | null; entries: unknown[] } | { unsupported: string | null } {
  if (!body || typeof body !== "object" || Array.isArray(body)) return { unsupported: null };
  const envelope = body as Record<string, unknown>;
  const version = text(envelope["schema_version"]);
  if (version !== DISCOVERY_SCHEMA_VERSION) return { unsupported: version };
  const entries = envelope[key];
  if (!Array.isArray(entries)) fail(`${key} must be an array`);
  return { observedAt: text(envelope["observed_at"]), entries: entries as unknown[] };
}

function project<T>(
  body: unknown,
  key: string,
  map: (entry: Record<string, unknown>) => T,
): DiscoveryState<T> {
  try {
    const head = collection(body, key);
    if ("unsupported" in head) return { kind: "unsupported", schemaVersion: head.unsupported };
    return {
      kind: "ready",
      observedAt: head.observedAt,
      // Every entry is mapped. One malformed entry fails the whole response rather
      // than quietly shrinking a list the user would read as complete.
      items: head.entries.map((entry, index) => {
        if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
          fail(`${key}[${index}] must be an object`);
        }
        return map(entry as Record<string, unknown>);
      }),
    };
  } catch (err) {
    if (err instanceof MalformedResponse) return { kind: "malformed", detail: err.message };
    throw err;
  }
}

export function projectConnections(body: MemberConnections | unknown): DiscoveryState<ConnectionView> {
  return project(body, "connections", entry => {
    const status = identity(entry, "configuration_status");
    return {
      connectionId: identity(entry, "connection_id"),
      integrationId: identity(entry, "integration_id"),
      ownership: identity(entry, "ownership"),
      actingIdentity: nullableText(entry, "acting_identity"),
      allowedResources: stringList(entry, "allowed_resources"),
      capabilities: stringList(entry, "capabilities"),
      configurationStatus: status,
      // Health is only ever "unknown"; a response claiming otherwise is not believed.
      observedHealth: "unknown",
      revision: integer(entry, "revision"),
      unusable: UNUSABLE_STATUSES.has(status),
    };
  });
}

export function projectTaskCatalog(body: TaskCatalog | unknown): DiscoveryState<TaskTemplateView> {
  return project(body, "templates", entry => {
    const templateId = identity(entry, "template_id");
    // An availability value this build does not recognise is not usable. Failing
    // closed on an enum is safe; a wrong *type* is a malformed payload.
    const available = required(entry, "availability") === "available";
    return {
      templateId,
      title: text(entry["title"]) ?? templateId,
      description: required(entry, "description"),
      available,
      // An available template carries no reason; anything unavailable keeps one.
      unavailableReason: available ? null : (nullableText(entry, "unavailable_reason") ?? "unknown"),
      requiredCapabilities: stringList(entry, "required_capabilities"),
      boundedContext: required(entry, "bounded_context"),
    };
  });
}
