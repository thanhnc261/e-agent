/** Forced colours (EA-14): selection, boundaries and the decision stay visible without author colours. */
import { expect, test } from "@playwright/test";
import { MockApi } from "../src/mock-api.ts";

test("forced colours keep the current section, controls and decision visible", async ({ page }) => {
  await page.emulateMedia({ forcedColors: "active" });
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  const current = page.locator('.ea-section-link[aria-current="page"]');
  await expect(current).toBeVisible();
  expect(await current.evaluate(node => getComputedStyle(node).outlineStyle)).toBe("solid");

  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  const approve = page.getByTestId("approval-approve");
  await expect(approve).toBeEnabled();
  for (const control of [approve, page.getByTestId("approval-reject"), page.getByTestId("run-state")]) {
    const width = await control.evaluate(node => parseFloat(getComputedStyle(node).borderTopWidth));
    expect(width).toBeGreaterThanOrEqual(1);
  }
  // Keyboard focus, so the focus-visible style applies as it would for a user.
  await page.getByTestId("approval-reject").focus();
  await page.keyboard.press("Shift+Tab");
  await expect(approve).toBeFocused();
  expect(await approve.evaluate(node => getComputedStyle(node).outlineStyle)).toBe("solid");
});
