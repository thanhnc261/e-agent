// @vitest-environment happy-dom
/**
 * Citations and the explanation, "grounded, not verified" (Task 4e.5, ADR 0033, ADR 0034 §3,
 * §4). Each test renders the result from a server evidence bundle and asserts what its name
 * claims: a citation's record and field are the server's, its value is read only from the
 * run's `actions[].approved_facts`, a digest-only citation is never a fact, model text is
 * labelled unverified and comes after the facts, and a grounded run never reads verified.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { RunController, emptyRunView, translate, type ControllerState, type Locale } from "@e-agent/ui-core";
import { RunProvider } from "@e-agent/ui-react";
import { Activity } from "../src/containers/Activity.tsx";
import { defaultSlots } from "../src/defaults.ts";
import { Explanation } from "../src/features/outcome/Explanation.tsx";
import { OutcomePanel } from "../src/features/outcome/OutcomePanel.tsx";
import { Timeline } from "../src/features/timeline/Timeline.tsx";

afterEach(cleanup);

type RunRecord = NonNullable<ControllerState["view"]["run"]>;
type RunEvent = ControllerState["view"]["events"][number];
type Client = ConstructorParameters<typeof RunController>[0]["client"];
type Bundle = Record<string, unknown>;

const D = (n: string) => `jcs-sha256-v1:${n.repeat(64).slice(0, 64)}`;
const UNRESOLVED_ID_DIGEST = D("a1");
const UNRESOLVED_POINTER_DIGEST = D("b2");
const SUMMARY = "Two orders are late: SO-SAMPLE-7 and SO-SAMPLE-9.";

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

function explanation(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    completeness: "known",
    run: {
      run_id: "run-1",
      goal: "which orders are late?",
      task_ref: null,
      task_ref_state: "none",
      requester_id: "u",
      driver_id: "fixture",
      state: "SUCCEEDED",
      reason_code: "grounded",
    },
    sources: [
      {
        evidence_id: "ev-orders-1",
        contract_id: "sales.order.read.v1",
        revision: "rev-17",
        label: "provider_read",
      },
    ],
    validation: { stages: [], open_findings: [], rules_evaluated: [], input_requests: [] },
    proposals: [],
    approvals: [],
    receipts: [],
    outcomes: [
      { action_id: null, status: "succeeded", event_id: null, step_id: null, label: "grounded_answer" },
    ],
    ...overrides,
  };
}

/** A run that ended `GROUNDED`: no action, the summary `unverified`, each citation `grounded`. */
function groundedBundle(): Bundle {
  return {
    schema: "e-agent-evidence-v1",
    run: { run_id: "run-1", revision: 3, state: "SUCCEEDED", reason_code: "grounded" },
    modes: { grounded_answers: "on" },
    actions: [],
    events: [],
    grounded_answer: {
      contract_id: "grounded.answer.v1",
      summary: { text: SUMMARY, label: "unverified" },
      citations: [
        { evidence_id: "ev-orders-1", pointer: "/orders/0/ref", value_digest: D("c3"), label: "grounded" },
        {
          evidence_id_digest: UNRESOLVED_ID_DIGEST,
          pointer_digest: UNRESOLVED_POINTER_DIGEST,
          value_digest: D("d4"),
          label: "grounded",
        },
      ],
    },
    explanation: explanation(),
  };
}

const ANSWER = "procurement.shortage.answer.v1";
const WRITE = "procurement.purchase-order.create-draft.v1";

/**
 * A typed answer in a run pinned `grounded_answers` as given. `withWriteFact` adds a superseded
 * write proposal that recorded the cited evidence as an approved fact, the one case where a
 * cited value can be shown (ADR 0034 §3).
 */
function typedBundle(mode: string, withWriteFact: boolean): Bundle {
  const fact = {
    contract_id: "procurement.demand.read.v1",
    data: { demand: { "product/ref": "P-SAMPLE-1", shortage: "33" } },
    evidence: { evidence_id: "ev-demand-1" },
  };
  return {
    schema: "e-agent-evidence-v1",
    run: { run_id: "run-1", revision: 5, state: "SUCCEEDED", reason_code: "verified" },
    modes: { grounded_answers: mode },
    actions: [
      ...(withWriteFact
        ? [
            {
              action_id: "a-write",
              contract_id: WRITE,
              state: "SUPERSEDED",
              arguments: {},
              approved_facts: [fact],
            },
          ]
        : []),
      { action_id: "a-answer", contract_id: ANSWER, state: "VERIFIED", arguments: {}, approved_facts: [] },
    ],
    events: [
      event(4, "proposal.created", {
        contract_id: ANSWER,
        citations: [
          { evidence_id: "ev-demand-1", pointer: "/demand/shortage", value_digest: D("e5") },
          { evidence_id: "ev-demand-1", pointer: "/demand/product~1ref", value_digest: D("f6") },
        ],
      }),
    ],
    explanation: explanation({
      run: { ...(explanation()["run"] as object), reason_code: "verified" },
      sources: [
        {
          evidence_id: "ev-demand-1",
          contract_id: "procurement.demand.read.v1",
          revision: "rev-4",
          label: "provider_read",
        },
      ],
      validation: {
        stages: [],
        open_findings: [],
        rules_evaluated: [{ rule_id: "PR-001", rule_version: "1", status: "PASS" }],
        input_requests: [],
      },
      proposals: [
        {
          action_id: "a-write",
          contract_id: WRITE,
          binding_id: null,
          connection_id: null,
          connection_version: null,
          credential_version: null,
          logical_operation_id: null,
          plan_id: null,
          step_index: null,
          supersedes_action_id: null,
          digest: D("0a"),
          evidence_ids: ["ev-demand-1"],
          state: "SUPERSEDED",
          label: "model_proposal",
          rationales: [
            {
              step_id: null,
              goal_ref: "run",
              cited_evidence: ["ev-demand-1"],
              rules_considered: ["PR-001"],
              alternatives: [],
              summary_digest: D("1b"),
              label: "model_authored",
            },
          ],
        },
      ],
      outcomes: [
        {
          action_id: "a-answer",
          status: "succeeded",
          event_id: "e9",
          step_id: null,
          label: "verified_outcome",
        },
      ],
    }),
  };
}

function controller(options: {
  bundle: Bundle | null;
  reasonCode: RunRecord["reason_code"];
  locale?: Locale;
  final?: string;
}) {
  const base = new RunController({ client: {} as Client, storage: null }).getState();
  const run: RunRecord = {
    run_id: "run-1",
    tenant_id: "t",
    requester_id: "u",
    task: "which orders are late?",
    state: "SUCCEEDED",
    revision: (options.bundle?.["run"] as { revision?: number } | undefined)?.revision ?? 3,
    logical_operation_id: "op-1",
    created_at: "2026-10-20T00:00:00Z",
    reason: null,
    reason_code: options.reasonCode,
  };
  const events = [
    event(1, "run.state_changed", { from: "CREATED", to: "RUNNING" }),
    ...(options.final ? [event(2, "message.final", { text: options.final })] : []),
    event(3, "run.state_changed", { from: "RUNNING", to: "SUCCEEDED" }),
  ];
  const state: ControllerState = {
    ...base,
    locale: options.locale ?? "en",
    runId: "run-1",
    evidence: options.bundle,
    view: { ...emptyRunView, run, events, lastSequence: events.length, finalMessage: options.final ?? null },
  };
  let loads = 0;
  const fake = {
    subscribe: () => () => {},
    getState: () => state,
    loadEvidence: async () => {
      loads += 1;
    },
  } as unknown as RunController;
  return { controller: fake, loads: () => loads };
}

function show(options: Parameters<typeof controller>[0], ui = <OutcomePanel />) {
  const c = controller(options);
  const r = render(<RunProvider controller={c.controller}>{ui}</RunProvider>);
  return { ...r, loads: c.loads };
}

const byTest = (root: ParentNode, id: string) => [
  ...root.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`),
];

describe("citations and the explanation (ADR 0034 §3, §4)", () => {
  it("a citation shows its record and field from the server", () => {
    const { container } = show({ bundle: groundedBundle(), reasonCode: "grounded" });
    const cited = byTest(container, "citation");
    expect(cited).toHaveLength(1);
    const record = byTest(cited[0]!, "citation-record")[0]!;
    // The record is the evidence id, resolved to the run's source: contract and revision.
    expect(record.textContent).toContain("ev-orders-1");
    expect(record.textContent).toContain("rev-17");
    expect(record.textContent).toMatch(/sales.*order.*read/i);
    expect(byTest(cited[0]!, "citation-field")[0]!.textContent).toBe("/orders/0/ref");
    // Each grounded-answer citation keeps the server's label, never "verified".
    expect(cited[0]!.getAttribute("data-label")).toBe("grounded");
    expect(cited[0]!.textContent).not.toContain(translate("en", "outcome.VERIFIED"));

    // A citation whose evidence id is not among the explanation's sources keeps its id and
    // pointer, and says its contract and revision were not recorded (EA-8).
    const bundle = groundedBundle();
    (bundle["explanation"] as Record<string, unknown>)["sources"] = [];
    cleanup();
    const again = show({ bundle, reasonCode: "grounded" }).container;
    const record2 = byTest(again, "citation-record")[0]!;
    expect(record2.textContent).toContain("ev-orders-1");
    expect(record2.textContent).toContain(translate("en", "explain.notRecorded"));
  });

  it("a grounded run says grounded, not verified (EN and VI)", () => {
    for (const locale of ["en", "vi"] as const) {
      const { container } = show({ bundle: groundedBundle(), reasonCode: "grounded", locale });
      const text = container.textContent ?? "";
      expect(byTest(container, "outcome-state")[0]!.textContent).toContain(
        translate(locale, "status.SUCCEEDED.grounded"),
      );
      expect(byTest(container, "outcome-grounded-explain")[0]!.textContent).toBe(
        translate(locale, "outcome.groundedExplain"),
      );
      // The explanation's outcome row reads the server's label, grounded_answer.
      const outcome = byTest(container, "explain-outcome")[0]!;
      expect(outcome.getAttribute("data-label")).toBe("grounded_answer");
      expect(outcome.textContent).toContain(translate(locale, "explain.label.grounded_answer"));
      // "grounded, not verified" itself contains "verified", so the check is on the verified
      // labels the UI has, which must be absent.
      for (const key of ["status.SUCCEEDED", "outcome.VERIFIED", "explain.label.verified_outcome"]) {
        expect(text, `${locale} ${key}`).not.toContain(translate(locale, key));
      }
      cleanup();
    }
    expect(translate("vi", "outcome.groundedExplain")).not.toBe(translate("en", "outcome.groundedExplain"));
  });

  it("free text outside citations is labelled unverified", () => {
    const { container } = show({ bundle: groundedBundle(), reasonCode: "grounded" });
    const words = byTest(container, "explain-agent-text");
    expect(words).toHaveLength(1);
    expect(words[0]!.getAttribute("data-label")).toBe("unverified");
    expect(words[0]!.textContent).toContain(SUMMARY);
    expect(words[0]!.textContent).toContain(translate("en", "outcome.agentText"));
    expect(words[0]!.textContent).toContain(translate("en", "explain.label.unverified"));
    // The summary is never inside a citation, and no citation reads as the agent's text.
    for (const c of byTest(container, "citation")) expect(c.textContent).not.toContain(SUMMARY);
    // A summary label the UI does not know is shown as unsupported, never as a fact.
    const bundle = groundedBundle();
    (bundle["grounded_answer"] as { summary: { label: string } }).summary.label = "certified";
    cleanup();
    const odd = byTest(show({ bundle, reasonCode: "grounded" }).container, "explain-agent-text")[0]!;
    expect(odd.getAttribute("data-label")).toBe("unsupported");
    expect(odd.textContent).toContain(translate("en", "explain.label.unsupported"));
    expect(odd.textContent).not.toContain("certified");
  });

  it("the explanation lists facts before any rationale", () => {
    const { container } = show({
      bundle: typedBundle("on", true),
      reasonCode: "verified",
      final: "Shortage is 40.",
    });
    const sections = byTest(container, "explain-section").map(s => s.getAttribute("data-section"));
    expect(sections).toEqual([
      "goal",
      "facts",
      "rules",
      "proposal",
      "rationale",
      "approval",
      "receipt",
      "outcome",
    ]);
    const facts = container.querySelector('[data-section="facts"]')!;
    const rationale = container.querySelector('[data-section="rationale"]')!;
    const citations = byTest(container, "citations")[0]!;
    // Source facts and the cited records come before the rationale refs.
    expect(facts.compareDocumentPosition(rationale) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(citations.compareDocumentPosition(rationale) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(facts.textContent).toContain("ev-demand-1");
    // The rationale is shown as the server holds it: ids, rule ids and a text digest.
    expect(rationale.textContent).toContain("PR-001");
    expect(rationale.textContent).toContain(D("1b"));
    expect(rationale.textContent).toContain(translate("en", "explain.rationaleIds"));
    // The agent's text, where there is any, comes after every fact; the grounded run shows it.
    cleanup();
    const grounded = show({ bundle: groundedBundle(), reasonCode: "grounded" }).container;
    const words = byTest(grounded, "explain-agent-text")[0]!;
    for (const id of ["citations", "explain-list"]) {
      const node = byTest(grounded, id)[0]!;
      expect(node.compareDocumentPosition(words) & Node.DOCUMENT_POSITION_FOLLOWING, id).toBeTruthy();
    }
  });

  it("an unresolved citation is never shown as a fact", () => {
    const { container } = show({ bundle: groundedBundle(), reasonCode: "grounded" });
    const unresolved = byTest(container, "citation-unresolved");
    expect(unresolved).toHaveLength(1);
    expect(unresolved[0]!.textContent).toContain(translate("en", "citation.unresolved"));
    // No record, field or value rows for it, and none of its digests anywhere in the result.
    expect(byTest(unresolved[0]!, "citation-record")).toHaveLength(0);
    expect(byTest(unresolved[0]!, "citation-value")).toHaveLength(0);
    const text = container.textContent ?? "";
    expect(text).not.toContain(UNRESOLVED_ID_DIGEST);
    expect(text).not.toContain(UNRESOLVED_POINTER_DIGEST);
    expect(text).not.toContain(D("d4"));
    // The one resolved citation is the only one shown as a record.
    expect(byTest(container, "citation")).toHaveLength(1);
  });

  it("a cited value comes from the run's approved facts, and an answer-only run shows value not recorded", () => {
    // A blocked or superseded write proposal recorded the evidence: the value at the pointer.
    const withFact = show({
      bundle: typedBundle("on", true),
      reasonCode: "verified",
      final: "Shortage is 40.",
    });
    const values = byTest(withFact.container, "citation-value");
    expect(values.map(v => v.getAttribute("data-recorded"))).toEqual(["true", "true"]);
    expect(values[0]!.textContent).toBe("33");
    // RFC 6901: "~1" is "/" inside a key.
    expect(values[1]!.textContent).toBe("P-SAMPLE-1");
    // Never from model text: the final message's number is not the value.
    for (const v of values) expect(v.textContent).not.toContain("40");
    cleanup();

    // An answer-only run: the answer's own action records no approved facts.
    const answerOnly = show({
      bundle: typedBundle("on", false),
      reasonCode: "verified",
      final: "Shortage is 40.",
    });
    const missing = byTest(answerOnly.container, "citation-value");
    expect(missing).toHaveLength(2);
    for (const v of missing) {
      expect(v.getAttribute("data-recorded")).toBe("false");
      expect(v.textContent).toBe(translate("en", "citation.valueNotRecorded"));
    }
    cleanup();

    // A grounded run has no action: record and field, value not recorded.
    const grounded = show({ bundle: groundedBundle(), reasonCode: "grounded" });
    expect(byTest(grounded.container, "citation-value").map(v => v.textContent)).toEqual([
      translate("en", "citation.valueNotRecorded"),
    ]);
    cleanup();

    // In shadow the typed answer's citations were recorded for comparison only: none shown.
    const shadow = show({ bundle: typedBundle("shadow", true), reasonCode: "verified" });
    expect(byTest(shadow.container, "citation")).toHaveLength(0);
    expect(byTest(shadow.container, "citations")).toHaveLength(0);
  });

  it("the explanation loads the bundle when opened, and says so while it is not read", () => {
    const { container, loads } = show({ bundle: null, reasonCode: "grounded" });
    const details = byTest(container, "explanation")[0] as HTMLDetailsElement;
    expect(byTest(container, "explain-list")).toHaveLength(0);
    expect(byTest(container, "explain-state")[0]!.getAttribute("data-state")).toBe("absent");
    details.open = true;
    // Two toggle events before any re-render (a double open) still read the bundle once.
    details.dispatchEvent(new Event("toggle"));
    details.dispatchEvent(new Event("toggle"));
    expect(loads()).toBe(1);
  });

  it("a verified answer's free-text field is never labelled verified", () => {
    // ADR 0034 §4: a free-text answer field such as `explanation` is never presented as
    // verified. The server labels no argument, so the values section claims no verification;
    // what was verified stays in the independent checks.
    const words = "Offer O-SAMPLE-2 is cheapest because the supplier is reliable.";
    for (const [locale, verified] of [
      ["en", /verif/i],
      ["vi", /xác minh/i],
    ] as const) {
      const c = controller({ bundle: null, reasonCode: "verified", locale });
      const base = c.controller.getState();
      const events = [
        ...base.view.events,
        event(4, "outcome.reported", {
          action_id: "a-answer",
          status: "VERIFIED",
          checks: [{ name: "offer_is_eligible", passed: true, observed: "eligible" }],
        }),
      ];
      const state = {
        ...base,
        view: {
          ...base.view,
          events,
          lastSequence: events.length,
          actions: [
            {
              action_id: "a-answer",
              contract_id: "procurement.offer.recommend.v1",
              state: "VERIFIED",
              arguments: { offer_ref: "O-SAMPLE-2", explanation: words },
            },
          ],
        },
      } as unknown as ControllerState;
      const live = { ...c.controller, getState: () => state } as unknown as RunController;
      const { container } = render(
        <RunProvider controller={live}>
          <OutcomePanel />
        </RunProvider>,
      );
      // The free text is shown, and no section around it carries a verified label.
      const value = [...container.querySelectorAll("dd")].find(dd => dd.textContent === words);
      expect(value, locale).toBeDefined();
      for (let node: Element | null = value!; node && node !== container; node = node.parentElement) {
        if (node.tagName === "DETAILS") {
          const summary = node.querySelector(":scope > summary")!.textContent ?? "";
          expect(summary, locale).toBe(translate(locale, "outcome.values"));
          expect(summary, locale).not.toMatch(verified);
        }
        const term = node.tagName === "DIV" ? node.querySelector(":scope > dt") : null;
        if (term) expect(term.textContent, locale).not.toMatch(verified);
      }
      // What was verified is still said, in the independent checks.
      expect(byTest(container, "outcome-check")).toHaveLength(1);
      expect(container.textContent).toContain(translate(locale, "outcome.checks"));
      cleanup();
    }
  });

  it("the activity offers the explanation for the attached run only", () => {
    // The default activity slot: the run's timeline, then its explanation once it has a result.
    const own = show({ bundle: groundedBundle(), reasonCode: "grounded" }, <Activity />);
    expect(byTest(own.container, "timeline")).toHaveLength(1);
    expect(byTest(own.container, "timeline-explanation")).toHaveLength(1);
    expect(defaultSlots.timeline).toBe(Activity);
    cleanup();
    // Before a result there is nothing to explain yet: the timeline alone.
    const c = controller({ bundle: groundedBundle(), reasonCode: null });
    const running = {
      ...c.controller.getState(),
      view: {
        ...c.controller.getState().view,
        run: { ...c.controller.getState().view.run!, state: "RUNNING" as const },
      },
    };
    const live = { ...c.controller, getState: () => running } as unknown as RunController;
    const before = render(
      <RunProvider controller={live}>
        <Activity />
      </RunProvider>,
    ).container;
    expect(byTest(before, "timeline")).toHaveLength(1);
    expect(byTest(before, "timeline-explanation")).toHaveLength(0);
    cleanup();
    // An earlier run's items, given by a layout to `Timeline`, have no bundle here: none.
    const items = [
      {
        sequence: 1,
        type: "run.created",
        labelKey: "event.run.created",
        occurredAt: "2026-10-20T00:00:00Z",
        supported: true,
        detail: null,
      },
    ];
    const earlier = show(
      { bundle: groundedBundle(), reasonCode: "grounded" },
      <Timeline items={items} reasonCode="grounded" />,
    );
    expect(byTest(earlier.container, "timeline")).toHaveLength(1);
    expect(byTest(earlier.container, "timeline-explanation")).toHaveLength(0);
    expect(byTest(earlier.container, "explanation")).toHaveLength(0);
  });

  it("an explanation the bundle does not hold says not recorded, never empty", () => {
    const bundle = groundedBundle();
    delete bundle["explanation"];
    const { container } = show({ bundle, reasonCode: "grounded" }, <Explanation />);
    expect(byTest(container, "explain-missing")[0]!.textContent).toBe(translate("en", "explain.missing"));
    // The citations still show, with their contract and revision not recorded.
    expect(byTest(container, "citation-record")[0]!.textContent).toContain(
      translate("en", "explain.notRecorded"),
    );
  });
});
