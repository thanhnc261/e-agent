import { describe, expect, it } from "vitest";
import { EAgentClient, type RunEvent } from "../src/index.ts";

function event(sequence: number): RunEvent {
  return {
    event_id: `evt-${sequence}`,
    tenant_id: "tenant-demo",
    run_id: "run-1",
    sequence,
    type: "read.recorded",
    schema_version: "1",
    occurred_at: "2026-10-12T00:00:00Z",
    payload: {},
  } as RunEvent;
}

/** A fake server with the real contract: default page 500, ceiling 1000, ordered by sequence. */
function fakeServer(total: number) {
  const all = Array.from({ length: total }, (_, i) => event(i + 1));
  const urls: string[] = [];
  const fetchImpl = (async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://api.test");
    urls.push(`${url.pathname}${url.search}`);
    const after = Number(url.searchParams.get("after_sequence") ?? 0);
    const limit = Math.min(Number(url.searchParams.get("limit") ?? 500), 1000);
    const page = all.filter((e) => e.sequence > after).slice(0, limit);
    return new Response(JSON.stringify(page), { status: 200 });
  }) as typeof fetch;
  return { fetchImpl, urls };
}

describe("EAgentClient.listEvents", () => {
  it("pages past the server cap and returns every event in order", async () => {
    const { fetchImpl, urls } = fakeServer(2305);
    const client = new EAgentClient({ fetch: fetchImpl });
    const events = await client.listEvents("run-1");
    expect(events).toHaveLength(2305);
    expect(events.map((e) => e.sequence)).toEqual(Array.from({ length: 2305 }, (_, i) => i + 1));
    expect(urls).toEqual([
      "/v1/runs/run-1/events?after_sequence=0&limit=1000",
      "/v1/runs/run-1/events?after_sequence=1000&limit=1000",
      "/v1/runs/run-1/events?after_sequence=2000&limit=1000",
    ]);
  });

  it("starts from afterSequence and does not duplicate the boundary event", async () => {
    const { fetchImpl } = fakeServer(1501);
    const client = new EAgentClient({ fetch: fetchImpl });
    const events = await client.listEvents("run-1", 400);
    expect(events[0]?.sequence).toBe(401);
    expect(events).toHaveLength(1101);
    expect(new Set(events.map((e) => e.sequence)).size).toBe(1101);
  });

  it("stops after one more empty page when the count is an exact multiple of the page", async () => {
    const { fetchImpl, urls } = fakeServer(1000);
    const events = await new EAgentClient({ fetch: fetchImpl }).listEvents("run-1");
    expect(events).toHaveLength(1000);
    expect(urls).toHaveLength(2);
  });

  it("returns an empty list for a run with no events", async () => {
    const { fetchImpl } = fakeServer(0);
    expect(await new EAgentClient({ fetch: fetchImpl }).listEvents("run-1")).toEqual([]);
  });
});
