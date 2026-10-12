/** Independent review regressions: route failure and explicit task detachment. */
import { expect, test } from "@playwright/test";
import { MockApi, RUN_ID } from "../src/index.ts";

test("a missing task deep link stops retrying after the unavailable response", async ({ page }) => {
  await new MockApi().install(page);
  let reads = 0;
  page.on("request", request => {
    if (new URL(request.url()).pathname === "/v1/runs/missing-task") reads += 1;
  });
  await page.goto("/#/task/missing-task");
  await expect.poll(() => reads).toBeGreaterThan(0);
  // Observe a bounded interval to detect a render-driven request loop.
  await page.waitForTimeout(500);
  expect(reads).toBeLessThanOrEqual(2);
});

test("new task remains detached after a task route has settled", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page).toHaveURL(new RegExp(`#/task/${RUN_ID}$`));
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  const reads = api.snapshotReads;
  await page.getByTestId("new-task").click();
  await page.waitForTimeout(300);
  await expect(page.getByTestId("composer-input")).toBeEnabled();
  await expect(page.getByTestId("approval-approve")).toHaveCount(0);
  expect(api.snapshotReads).toBe(reads);
  expect(api.decisions).toHaveLength(0);
  expect(api.createRuns).toBe(1);
});

test("malformed URL encoding has a usable fallback instead of crashing", async ({ page }) => {
  await new MockApi().install(page);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/#/task/%");
  await expect(page.getByTestId("composer-input")).toBeVisible();
  expect(errors).toEqual([]);
});
