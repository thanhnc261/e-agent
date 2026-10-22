/**
 * Citations and the explanation in the workspace (Task 4e.5, ADR 0034 §3, §4, plan Review
 * Focus 8: the UI never claims more than the server says). Every spec runs against the
 * conformance mock with `features.conversations: on`; the bundle is the server's shape, and
 * every label asserted below is one the bundle carries.
 */
import { expect, test, type Page } from "@playwright/test";
import {
  GROUNDED_EVIDENCE_ID,
  GROUNDED_SUMMARY,
  MockApi,
  RUN_ID,
  UNRESOLVED_CITATION_DIGEST,
  runAxe,
} from "../src/index.ts";

function groundedThread(): MockApi {
  const api = new MockApi();
  api.features = "on";
  api.twoRunThread();
  api.groundedEnd(RUN_ID);
  return api;
}

/** Open the conversation from the sidebar; the workspace opens by itself for the result. */
async function openGrounded(page: Page, api: MockApi, url = "/"): Promise<void> {
  await api.install(page);
  await page.goto(url);
  const row = page.getByTestId("thread-row").first();
  await row.waitFor({ state: "attached" });
  if (!(await row.isVisible())) await page.getByTestId("thread-list-toggle").click();
  await row.click();
  await expect(page.getByTestId("artifact-workspace")).toBeVisible();
}

const VERIFIED_LABELS = ["Completed · verified", "Outcome verified", "Verified by an independent check"];

test("explanation opens from the outcome", async ({ page }) => {
  const api = groundedThread();
  await openGrounded(page, api);
  const ws = page.getByTestId("artifact-workspace");
  const outcome = ws.getByTestId("outcome");

  // The result says what the server's reason code says: grounded, not verified (PR-19).
  await expect(outcome.getByTestId("outcome-state")).toContainText("Completed · grounded, not verified");
  await expect(outcome.getByTestId("outcome-grounded-explain")).toHaveText(
    "Grounded: its sources are records this task read. Not verified: nothing read the result back independently.",
  );
  await expect(page.getByTestId("thread-run").nth(1).getByTestId("run-card-status")).toHaveText(
    /grounded, not verified/,
  );
  // Nothing is read for the explanation until it is opened.
  expect(api.evidenceReads).toBe(0);

  const explanation = outcome.getByTestId("explanation");
  await explanation.locator(":scope > summary").click();
  await expect(explanation.getByTestId("explain-list")).toBeVisible();
  expect(api.evidenceReads).toBe(1);

  // The citation: its record and field from the server, and no value, since a grounded run
  // has no action and so no approved fact (ADR 0034 §3).
  const cited = explanation.getByTestId("citation");
  await expect(cited).toHaveCount(1);
  await expect(cited).toHaveAttribute("data-label", "grounded");
  await expect(cited.getByTestId("citation-record")).toContainText(GROUNDED_EVIDENCE_ID);
  await expect(cited.getByTestId("citation-record")).toContainText("rev-17");
  await expect(cited.getByTestId("citation-field")).toHaveText("/orders/0/ref");
  await expect(cited.getByTestId("citation-value")).toHaveText("Value not recorded");
  await expect(cited.getByTestId("citation-value")).toHaveAttribute("data-recorded", "false");
  // The digest-only citation is never a fact, and none of its digests reach the page.
  await expect(explanation.getByTestId("citation-unresolved")).toHaveText(
    /A source that could not be matched/,
  );
  await expect(page.locator("body")).not.toContainText(UNRESOLVED_CITATION_DIGEST);

  // Every status label in the explanation is the bundle's.
  await expect(explanation.getByTestId("explain-outcome")).toHaveAttribute("data-label", "grounded_answer");
  await expect(explanation.getByTestId("explain-outcome")).toContainText("Grounded, not verified");
  // The server's stage status in the user's language, not its enum (G-D 4.U6).
  await expect(explanation.getByTestId("explain-outcome")).toContainText(
    "Grounded, not verified · Succeeded",
  );
  const words = explanation.getByTestId("explain-agent-text");
  await expect(words).toHaveAttribute("data-label", "unverified");
  await expect(words).toContainText("The agent's words");
  await expect(words).toContainText("Not verified");
  await expect(words).toContainText(GROUNDED_SUMMARY);
  for (const label of VERIFIED_LABELS) await expect(ws).not.toContainText(label);

  // The explanation opens from the activity too, from the same bundle, read once.
  await ws.getByTestId("workspace-tab-activity").click();
  await ws.getByTestId("timeline").locator(":scope > summary").click();
  const fromActivity = ws.getByTestId("timeline-explanation");
  await fromActivity.locator(":scope > summary").click();
  await expect(fromActivity.getByTestId("explain-section")).toHaveCount(8);
  await expect(fromActivity.getByTestId("explain-outcome")).toHaveAttribute("data-label", "grounded_answer");
  expect(api.evidenceReads).toBe(1);
  // Opening it decided, sent and started nothing.
  expect(api.decisions).toHaveLength(0);
  expect(api.messages).toHaveLength(0);
  expect(api.messageStarts).toBe(0);
});

test("a verified answer's citation shows the value its run recorded, and reads verified", async ({
  page,
}) => {
  const api = new MockApi();
  api.features = "on";
  api.twoRunThread();
  api.finish(RUN_ID, "The shortage is 40 (sample).");
  api.run(RUN_ID).reasonCode = "verified";
  api.evidence = {
    schema: "e-agent-evidence-v1",
    run: api.snapshot(RUN_ID).run,
    modes: { grounded_answers: "on" },
    actions: [
      {
        action_id: "a-write",
        contract_id: "procurement.purchase-order.create-draft.v1",
        state: "SUPERSEDED",
        approved_facts: [
          {
            contract_id: "procurement.demand.read.v1",
            data: { shortage: "33" },
            evidence: { evidence_id: "ev-demand-1" },
          },
        ],
      },
      {
        action_id: "a-answer",
        contract_id: "procurement.shortage.answer.v1",
        state: "VERIFIED",
        approved_facts: [],
      },
    ],
    events: [
      {
        event_id: "e-p",
        sequence: 4,
        type: "proposal.created",
        schema_version: "1",
        payload: {
          contract_id: "procurement.shortage.answer.v1",
          citations: [
            {
              evidence_id: "ev-demand-1",
              pointer: "/shortage",
              value_digest: `jcs-sha256-v1:${"e5".repeat(32)}`,
            },
          ],
        },
      },
    ],
    explanation: {
      completeness: "known",
      run: { goal: "draft a PO for it" },
      sources: [
        {
          evidence_id: "ev-demand-1",
          contract_id: "procurement.demand.read.v1",
          revision: "rev-4",
          label: "provider_read",
        },
      ],
      validation: { rules_evaluated: [] },
      proposals: [],
      approvals: [],
      receipts: [],
      outcomes: [
        {
          action_id: "a-answer",
          status: "succeeded",
          event_id: "e9",
          step_id: null,
          label: "verified_outcome",
        },
      ],
    },
  };
  await openGrounded(page, api);
  const explanation = page
    .getByTestId("artifact-workspace")
    .getByTestId("outcome")
    .getByTestId("explanation");
  await explanation.locator(":scope > summary").click();
  const value = explanation.getByTestId("citation-value");
  // The value is the approved fact's at the pointer, never the 40 of the agent's text.
  await expect(value).toHaveText("33");
  await expect(value).toHaveAttribute("data-recorded", "true");
  // A typed answer's citation carries no label of its own; verified is the outcome's, from the server.
  await expect(explanation.getByTestId("citation")).not.toHaveAttribute("data-label", /.+/);
  await expect(explanation.getByTestId("explain-outcome")).toHaveAttribute("data-label", "verified_outcome");
  await expect(explanation.getByTestId("explain-outcome")).toContainText("Verified by an independent check");
});

const AXE_STATES: { name: string; reach: (page: Page) => Promise<void> }[] = [
  ...(["light", "dark", "high-contrast"] as const).map(theme => ({
    name: `grounded explanation open (${theme})`,
    reach: async (page: Page) => {
      await openGrounded(page, groundedThread(), `/?theme=${theme}`);
      const explanation = page.getByTestId("artifact-workspace").getByTestId("explanation");
      await explanation.locator(":scope > summary").click();
      await expect(explanation.getByTestId("citation-unresolved")).toBeVisible();
    },
  })),
  {
    name: "explanation from the activity",
    reach: async (page: Page) => {
      await openGrounded(page, groundedThread());
      const ws = page.getByTestId("artifact-workspace");
      await ws.getByTestId("workspace-tab-activity").click();
      await ws.getByTestId("timeline").locator(":scope > summary").click();
      const fromActivity = ws.getByTestId("timeline-explanation");
      await fromActivity.locator(":scope > summary").click();
      await expect(fromActivity.getByTestId("explain-list")).toBeVisible();
    },
  },
];

for (const state of AXE_STATES) {
  test(`axe: explanation state "${state.name}" has no WCAG 2.2 AA violation`, async ({ page }) => {
    await state.reach(page);
    const result = await runAxe(page);
    // The count is printed so a run shows how many rules it checked (PR-31).
    console.log(`axe ${state.name}: ${result.rules} rules, ${result.violations.length} violations`);
    expect(result.rules, "axe ran no rule").toBeGreaterThan(0);
    expect(result.violations).toEqual([]);
  });
}
