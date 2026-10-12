/**
 * Route parsing (frontend development guide §3): a small typed union, an explicit
 * fallback for anything unknown, and no secret or task text in the URL.
 */
import { describe, expect, it } from "vitest";
import { DEFAULT_ROUTE, formatRoute, parseRoute, sameRoute } from "../src/app/routes.ts";

describe("standalone routes", () => {
  it("parses the supported routes with and without a leading slash", () => {
    expect(parseRoute("")).toEqual({ name: "overview" });
    expect(parseRoute("#")).toEqual({ name: "overview" });
    expect(parseRoute("#/")).toEqual({ name: "overview" });
    expect(parseRoute("#/overview")).toEqual({ name: "overview" });
    // Session work was folded into Recent tasks (owner review 2026-10-12).
    expect(parseRoute("#work")).toEqual(DEFAULT_ROUTE);
    expect(parseRoute("#/connections")).toEqual({ name: "connections" });
    expect(parseRoute("#/task")).toEqual({ name: "task", runId: null });
    expect(parseRoute("#/task/run-1")).toEqual({ name: "task", runId: "run-1" });
  });

  it("falls back for an unknown route instead of failing open", () => {
    expect(parseRoute("#/../admin")).toEqual(DEFAULT_ROUTE);
    expect(parseRoute("#/settings")).toEqual(DEFAULT_ROUTE);
  });

  it("drops a run id that is not a plausible opaque identifier", () => {
    expect(parseRoute("#/task/" + encodeURIComponent("../../etc"))).toEqual({ name: "task", runId: null });
    expect(parseRoute("#/task/" + encodeURIComponent("<script>"))).toEqual({ name: "task", runId: null });
    expect(parseRoute(`#/task/${"x".repeat(200)}`)).toEqual({ name: "task", runId: null });
  });

  it("round-trips and compares routes", () => {
    for (const hash of ["#/overview", "#/connections", "#/task", "#/task/run-1"]) {
      expect(formatRoute(parseRoute(hash))).toBe(hash);
    }
    expect(sameRoute({ name: "task", runId: "a" }, { name: "task", runId: "a" })).toBe(true);
    expect(sameRoute({ name: "task", runId: "a" }, { name: "task", runId: "b" })).toBe(false);
  });
});

describe("malformed addresses", () => {
  it("treats malformed percent-encoding as no run id instead of throwing", () => {
    for (const hash of ["#/task/%", "#/task/%E0%A4%A", "#/task/%zz", "#/task/%%"]) {
      expect(() => parseRoute(hash), hash).not.toThrow();
      expect(parseRoute(hash), hash).toEqual({ name: "task", runId: null });
    }
  });

  it("never throws for any single-character suffix", () => {
    for (let code = 32; code < 127; code += 1) {
      const hash = `#/task/${String.fromCharCode(code)}`;
      expect(() => parseRoute(hash), hash).not.toThrow();
    }
  });

  it("keeps a malformed encoding out of other routes too", () => {
    expect(() => parseRoute("#/%")).not.toThrow();
    expect(parseRoute("#/%")).toEqual(DEFAULT_ROUTE);
  });
});
