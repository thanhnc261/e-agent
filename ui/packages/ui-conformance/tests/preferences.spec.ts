/** Preferences remain usable by keyboard in both the document and shadow root. */
import { expect, test } from "@playwright/test";
import { MockApi } from "../src/mock-api.ts";

for (const host of ["/", "/host.html"]) {
  test(`preferences keyboard navigation and focus return: ${host}`, async ({ page }) => {
    await new MockApi().install(page);
    await page.goto(host);
    if (host.includes("host")) await page.getByTestId("overlay-launcher").click();
    const trigger = page.getByTestId("preferences-toggle");
    await trigger.focus();
    await trigger.press("Enter");
    await expect(page.getByTestId("preferences-panel")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Language", { exact: true })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("preferences-panel")).not.toBeVisible();
    await expect(trigger).toBeFocused();
    if (host.includes("host")) await expect(page.getByTestId("overlay-panel")).toBeVisible();
  });
}

// Conversation first (owner decision EA-10; owner review 2026-10-12): the overview is
// the composer and the user's recent prompts. Installed task types live on the
// Capabilities page, and a recent prompt only refills the composer.
test("overview is the composer and recent prompts, without horizontal overflow", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/");
  await expect(page.getByTestId("ai-disclosure")).toBeVisible();
  await expect(page.getByTestId("task-catalog")).toHaveCount(0);
  await expect(page.getByTestId("recent-prompts")).toHaveCount(0);
  const composer = await page.getByTestId("composer-input").boundingBox();
  expect(composer!.width).toBeLessThanOrEqual(760);

  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await page.getByTestId("new-task").click();
  await expect(page.getByTestId("page-overview")).toBeVisible();
  const runs = api.createRuns;
  await page.getByTestId("recent-prompt").first().click();
  await expect(page.getByTestId("composer-input")).toHaveValue("restock");
  await expect(page.getByTestId("composer-input")).toBeFocused();
  expect(api.createRuns).toBe(runs);

  await page.setViewportSize({ width: 320, height: 700 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await page.getByTestId("preferences-toggle").click();
  const preferences = await page.getByTestId("preferences-panel").boundingBox();
  expect(preferences!.x).toBeGreaterThanOrEqual(0);
  expect(preferences!.x + preferences!.width).toBeLessThanOrEqual(320);
});
