/**
 * Approval digest check (ADR 0006): RFC 8785 JCS over the number-free profile,
 * SHA-256 via WebCrypto. Must reproduce the Python implementation exactly; both
 * are tested against packages/contracts golden vectors.
 */
export const DIGEST_PROFILE = "jcs-sha256-v1";

export class CanonicalizationError extends Error {}

function utf16Compare(a: string, b: string): number {
  // JS strings are UTF-16; relational comparison is by code unit, as JCS requires.
  return a < b ? -1 : a > b ? 1 : 0;
}

function encodeString(value: string, path: string): string {
  if (!value.isWellFormed()) throw new CanonicalizationError(`lone surrogate at ${path}`);
  // JSON.stringify escapes exactly the RFC 8785 set: quote, backslash, \b\t\n\f\r and
  // other C0 controls as lowercase \u00xx; everything else stays literal.
  return JSON.stringify(value);
}

export function canonicalize(value: unknown, path = "$"): string {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "string") return encodeString(value, path);
  if (typeof value === "number" || typeof value === "bigint") {
    throw new CanonicalizationError(`JSON numbers are not allowed in the profile at ${path}`);
  }
  if (Array.isArray(value)) {
    return `[${value.map((v, i) => canonicalize(v, `${path}[${i}]`)).join(",")}]`;
  }
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort(utf16Compare);
    return `{${keys.map((k) => `${encodeString(k, path)}:${canonicalize(obj[k], `${path}.${k}`)}`).join(",")}}`;
  }
  throw new CanonicalizationError(`unsupported type ${typeof value} at ${path}`);
}

export async function digest(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalize(value));
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const hex = Array.from(hash, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${DIGEST_PROFILE}:${hex}`;
}

/** True only when the server's digest matches our recomputation of the shown proposal. */
export async function verifyDigest(canonicalProposal: unknown, expected: string): Promise<boolean> {
  try {
    return (await digest(canonicalProposal)) === expected;
  } catch {
    return false;
  }
}
