/**
 * Error envelope detection (ADR 0023, Phase 4 Task 4e.3). The UI falls back to today's
 * routes only for a route that is not mounted, which answers without e-agent's envelope.
 */
import { describe, expect, it } from "vitest";
import { ApiError, EAgentClient } from "../src/index.ts";

function clientAnswering(response: () => Response): EAgentClient {
  return new EAgentClient({ fetch: (async () => response()) as typeof fetch });
}

async function failure(client: EAgentClient): Promise<ApiError> {
  try {
    await client.createConversation();
  } catch (err) {
    if (err instanceof ApiError) return err;
    throw err;
  }
  throw new Error("expected an ApiError");
}

describe("EAgentClient error envelope", () => {
  it("an enveloped NOT_FOUND keeps its code, message and correlation id", async () => {
    const err = await failure(
      clientAnswering(
        () =>
          new Response(JSON.stringify({ code: "NOT_FOUND", message: "conversations are off", correlation_id: "corr-1" }), {
            status: 404,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    expect(err).toMatchObject({ status: 404, code: "NOT_FOUND", message: "conversations are off", enveloped: true, correlationId: "corr-1" });
  });

  it("FastAPI's own 404 body has no envelope", async () => {
    const err = await failure(
      clientAnswering(
        () => new Response(JSON.stringify({ detail: "Not Found" }), { status: 404, statusText: "Not Found", headers: { "Content-Type": "application/json" } }),
      ),
    );
    expect(err).toMatchObject({ status: 404, code: "HTTP_ERROR", enveloped: false, correlationId: null });
  });

  it("a static mount's plain-text 405 is an ApiError without an envelope, not a parse error", async () => {
    const err = await failure(
      clientAnswering(
        () => new Response("Method Not Allowed", { status: 405, statusText: "Method Not Allowed", headers: { "Content-Type": "text/plain" } }),
      ),
    );
    expect(err).toMatchObject({ status: 405, code: "HTTP_ERROR", message: "Method Not Allowed", enveloped: false });
  });
});
