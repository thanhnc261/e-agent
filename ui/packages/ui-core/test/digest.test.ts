import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CanonicalizationError, canonicalize, digest, verifyDigest } from "../src/digest.ts";

const golden = JSON.parse(
  readFileSync(
    fileURLToPath(new URL("../../../../packages/contracts/src/e_agent/contracts/golden/digest_vectors.json", import.meta.url)),
    "utf8",
  ),
) as { vectors: { name: string; input: unknown; canonical: string; digest?: string }[] };

describe("JCS digest (shared golden vectors with Python)", () => {
  for (const v of golden.vectors) {
    it(v.name, async () => {
      expect(canonicalize(v.input)).toBe(v.canonical);
      if (v.digest) expect(await digest(v.input)).toBe(v.digest);
    });
  }

  it("rejects JSON numbers and lone surrogates", () => {
    expect(() => canonicalize({ q: 1 })).toThrow(CanonicalizationError);
    expect(() => canonicalize({ s: "\ud800" })).toThrow(CanonicalizationError);
  });

  it("verifies only an exact match", async () => {
    const proposal = { arguments: { quantity: "40" } };
    const d = await digest(proposal);
    expect(d).toMatch(/^jcs-sha256-v1:[0-9a-f]{64}$/);
    expect(await verifyDigest(proposal, d)).toBe(true);
    expect(await verifyDigest({ arguments: { quantity: "41" } }, d)).toBe(false);
    expect(await verifyDigest({ q: 1 }, d)).toBe(false);
  });
});
