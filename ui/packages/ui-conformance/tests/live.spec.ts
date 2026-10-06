/**
 * Live UI workflow (I09) against the real server and kernel (fixture profile):
 * complete and reject the procurement run in each UI; reload never re-executes.
 */
import { expect, test, type Page } from "@playwright/test";
import { TARGETS } from "../src/targets.ts";

async function start(page: Page, url: string, open: (p: Page) => Promise<void>) {
  await page.goto(url);
  await open(page);
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled({ timeout: 15_000 });
}

for (const target of TARGETS) {
  test.describe(`${target.name} UI (live fixture server)`, () => {
    test("completes the draft purchase order with verified outcome and evidence", async ({ page }) => {
      await start(page, target.url(), target.open);
      await expect(page.getByTestId("material-field").first()).toBeVisible();
      await page.getByTestId("approval-approve").click();
      await page.getByTestId("approval-confirm").click();
      await expect(page.locator('[data-testid="outcome-state"][data-state="SUCCEEDED"]')).toBeVisible({ timeout: 15_000 });
      await expect(page.locator('[data-testid="action"][data-state="VERIFIED"]')).toHaveCount(1);
      await expect(page.getByTestId("final-message")).toContainText("draft purchase order");
      await page.getByTestId("evidence-load").click();
      await expect(page.getByTestId("evidence-bundle")).toContainText("e-agent-evidence-v1");
    });

    test("reject writes nothing", async ({ page }) => {
      await start(page, target.url(), target.open);
      await page.getByTestId("approval-reject").click();
      await expect(page.getByTestId("outcome-state")).not.toHaveAttribute("data-state", /WAITING_APPROVAL|RUNNING/, { timeout: 15_000 });
      await expect(page.locator('[data-testid="action"][data-state="VERIFIED"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="action"][data-state="COMMITTED"]')).toHaveCount(0);
    });

    test("reload after approval resumes the same run and never executes twice", async ({ page }) => {
      await start(page, target.url(), target.open);
      await page.getByTestId("approval-approve").click();
      await page.getByTestId("approval-confirm").click();
      await page.reload();
      await target.open(page);
      await expect(page.locator('[data-testid="outcome-state"][data-state="SUCCEEDED"]')).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("action")).toHaveCount(1);
      const created = page.getByTestId("timeline-item").filter({ hasText: /Run created|Đã tạo/ });
      await expect(created).toHaveCount(1);
    });
  });
}
