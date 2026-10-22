// @vitest-environment happy-dom
/**
 * Chat defects UX review (docs/reviews/2026-10-20-chat-defects-ux-review.md), owner G-0
 * 2026-10-20. Each test is named after the finding it closes.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import {
  RunController,
  emptyRunView,
  reduceRunView,
  translate,
  type ControllerState,
  type Locale,
} from "@e-agent/ui-core";
import { RunProvider } from "@e-agent/ui-react";
import { ContextPreview } from "../src/features/composer/ContextPreview.tsx";
import { Messages } from "../src/features/conversation/Messages.tsx";
import { TaskNavigation } from "../src/features/task-navigation/TaskNavigation.tsx";
import { Timeline } from "../src/features/timeline/Timeline.tsx";

afterEach(cleanup);

type RunRecord = NonNullable<ControllerState["view"]["run"]>;
type RunEvent = ControllerState["view"]["events"][number];
type Client = ConstructorParameters<typeof RunController>[0]["client"];

function event(sequence: number, type: string, payload: Record<string, unknown>): RunEvent {
  return {
    event_id: `e${sequence}`,
    tenant_id: "t",
    run_id: "run-1",
    sequence,
    type,
    occurred_at: "2026-10-20T00:00:00Z",
    payload,
    schema_version: "1",
  } as RunEvent;
}

/** hi → reply → hi → reply, waiting on the second reply. */
const TWO_REPLIES = [
  event(1, "input.requested", { question: "Hello! What next?", kind: "reply" }),
  event(2, "run.state_changed", { from: "RUNNING", to: "WAITING_INPUT" }),
  event(3, "input.received", { input: "hi" }),
  event(4, "run.state_changed", { from: "WAITING_INPUT", to: "RUNNING" }),
  event(5, "input.requested", { question: "Hello again! What next?", kind: "reply" }),
  event(6, "run.state_changed", { from: "RUNNING", to: "WAITING_INPUT" }),
];

function controller(
  options: {
    events?: RunEvent[];
    history?: ControllerState["history"];
    locale?: Locale;
  } = {},
): RunController {
  const base = new RunController({ client: {} as Client, storage: null }).getState();
  const run: RunRecord = {
    run_id: "run-1",
    tenant_id: "t",
    requester_id: "u",
    task: "hi",
    state: "WAITING_INPUT",
    revision: 3,
    logical_operation_id: "op-1",
    created_at: "2026-10-20T00:00:00Z",
    reason: null,
  };
  const view = reduceRunView(
    reduceRunView(emptyRunView, {
      type: "snapshot",
      snapshot: { run, latest_sequence: 0, actions: [], pending_approval: null },
    }),
    { type: "events", events: options.events ?? [] },
  );
  const state: ControllerState = {
    ...base,
    runId: "run-1",
    locale: options.locale ?? "en",
    history: options.history ?? [],
    view,
  };
  return {
    subscribe: () => () => {},
    getState: () => state,
    hostContextPreview: () => null,
  } as unknown as RunController;
}

describe("F-4 Context panel splits what is sent from what is used", () => {
  for (const locale of ["en", "vi"] as const) {
    it(`F-4 drops the lead-in and the hints line with no page context (${locale})`, () => {
      const { getByTestId, container } = render(
        <RunProvider controller={controller({ locale })}>
          <ContextPreview />
        </RunProvider>,
      );
      const panel = getByTestId("context-panel");
      const text = panel.textContent ?? "";
      expect(text).not.toContain(translate(locale, "context.message"));
      expect(text).not.toContain(translate(locale, "context.server"));
      expect(getByTestId("context-sent").textContent).toBe(translate(locale, "context.sentNoHost"));
      expect(getByTestId("context-none").textContent).toBe(translate(locale, "context.noHost"));
      // The "sent" line sits under the panel title; the "used" line is its own block.
      expect(container.querySelector(".ea-context-uses [data-testid=context-none]")).not.toBeNull();
    });
  }
});

describe("F-5 Activity names a reply wait like the composer", () => {
  it("F-5 the timeline reads Your turn after a reply", () => {
    const { getAllByTestId } = render(
      <RunProvider controller={controller({ events: TWO_REPLIES })}>
        <Timeline />
      </RunProvider>,
    );
    const rows = getAllByTestId("timeline-item").filter(r => r.dataset["type"] === "run.state_changed");
    const turn = translate("en", "status.WAITING_INPUT.reply");
    const answer = translate("en", "status.WAITING_INPUT");
    expect(rows.at(-1)?.textContent).toContain(turn);
    expect(rows[1]?.textContent).toContain(`${turn} →`);
    for (const row of rows) expect(row.textContent).not.toContain(answer);
  });
});

describe("F-6 later replies stay visibly unverified", () => {
  it("F-6 a later reply shows a small visible not-verified note", () => {
    const { getAllByTestId, getByTestId } = render(
      <RunProvider controller={controller({ events: TWO_REPLIES })}>
        <Messages />
      </RunProvider>,
    );
    expect(getAllByTestId("reply-label")).toHaveLength(1);
    const notes = getAllByTestId("reply-note");
    expect(notes).toHaveLength(1);
    expect(notes[0]?.textContent).toContain(translate("en", "conversation.replyNote"));
    expect(notes[0]?.className).toContain("ea-muted");
    expect(notes[0]?.className).not.toContain("ea-visually-hidden");
    expect(notes[0]?.closest(".ea-message")?.contains(getByTestId("pending-reply"))).toBe(true);
  });
});

describe("F-8 sidebar status pairs a marker with its text", () => {
  it("F-8 the history item shows the composer's status marker", () => {
    const { getByTestId } = render(
      <RunProvider
        controller={controller({
          history: [{ runId: "run-1", task: "hi", state: "WAITING_INPUT", replyPending: true }],
        })}
      >
        <TaskNavigation />
      </RunProvider>,
    );
    const item = getByTestId("history-task");
    const marker = item.querySelector("[data-testid=history-status-marker]");
    expect(marker?.textContent).toBe("◆");
    expect(marker?.getAttribute("aria-hidden")).toBe("true");
    expect(item.textContent).toContain(translate("en", "status.WAITING_INPUT.reply"));
  });
});
