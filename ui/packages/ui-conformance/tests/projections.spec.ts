/**
 * Typed projections at the browser boundary (enterprise overlay adoption plan FE-03).
 * Missing provenance stays unknown, an unrecognised audit format is reported rather
 * than rendered, and a check without a recorded verdict is never shown as a pass or
 * a failure.
 */
import { expect, test } from "@playwright/test";
import { MockApi } from "../src/index.ts";

async function openEvidence(page: import("@playwright/test").Page) {
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("run-task")).toBeVisible();
  await page.getByTestId("evidence").locator(":scope > summary").click();
  await page.getByTestId("evidence-load").click();
}

test("missing source provenance is shown as unknown, never as empty or complete", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  api.evidence = {
    schema: "e-agent-evidence-v1",
    actions: [
      {
        approved_facts: [
          { contract_id: "demand.read.v1", data: { shortage: "33" }, evidence: { evidence_id: "ev-1" } },
          {
            contract_id: "demand.read.v1",
            data: { available: "7" },
            evidence: {
              evidence_id: "ev-2",
              source: "inventory",
              locator: "stock/widget-a",
              observed_at: "2026-10-09T01:02:03Z",
              completeness: "partial",
            },
          },
        ],
      },
    ],
  };
  await api.install(page);
  await page.goto("/");
  await openEvidence(page);

  const sources = page.getByTestId("evidence-source");
  await expect(sources).toHaveCount(2);
  await expect(sources.first()).toContainText("Not available");
  await expect(sources.first().locator("small")).toHaveAttribute("data-completeness", "unknown");
  await expect(sources.first()).toContainText("Completeness unknown");
  await expect(sources.nth(1)).toContainText("inventory");
  await expect(sources.nth(1)).toContainText("Partial observation");
  await expect(sources.nth(1).locator("small")).toHaveAttribute("data-completeness", "partial");
});

test("an unrecognised audit format is reported instead of rendered", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  api.evidence = { schema: "e-agent-evidence-v99", actions: [] };
  await api.install(page);
  await page.goto("/");
  await openEvidence(page);
  await expect(page.getByTestId("evidence-unsupported")).toContainText("does not understand");
  await expect(page.getByTestId("evidence-source")).toHaveCount(0);
  // The raw record stays inspectable even when this version cannot project it.
  await expect(page.getByTestId("evidence-bundle")).toContainText("e-agent-evidence-v99");
});

test("a check with no recorded verdict stays unknown in the result", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await page.getByTestId("approval-approve").click();
  await page.getByTestId("approval-confirm").click();

  api.emit("outcome.reported", {
    action_id: "act-1",
    status: "VERIFIED",
    checks: [{ name: "quantity", passed: true, observed: "40" }, { name: "receipt_present" }],
  });
  api.emit("run.state_changed", { from: "VERIFYING", to: "SUCCEEDED" });
  api.state = "SUCCEEDED";

  await expect(page.getByTestId("outcome-state")).toHaveAttribute("data-status", "verified");
  const checks = page.getByTestId("outcome-check");
  await expect(checks).toHaveCount(2);
  await expect(checks.nth(0)).toHaveAttribute("data-passed", "true");
  await expect(checks.nth(1)).toHaveAttribute("data-passed", "null");
  await expect(checks.nth(1)).toContainText("No result recorded");
});
