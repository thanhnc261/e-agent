/** Route changes must take precedence over the previously attached run. */
import { expect, test } from "@playwright/test";
import { MockApi, RUN_ID } from "../src/index.ts";

test("opening an unavailable task from an active task preserves the requested address", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page).toHaveURL(new RegExp(`#/task/${RUN_ID}$`));
  await expect(page.getByTestId("approval-approve")).toBeEnabled();

  await page.evaluate(() => {
    location.hash = "#/task/missing-task";
  });
  await expect(page.getByTestId("task-unavailable")).toBeVisible();
  await expect(page).toHaveURL(/#\/task\/missing-task$/);
  expect(api.createRuns).toBe(1);
  expect(api.decisions).toHaveLength(0);
});
