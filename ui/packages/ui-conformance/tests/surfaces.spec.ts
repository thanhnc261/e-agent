import { expect, test } from "@playwright/test";
import { MockApi } from "../src/mock-api.ts";

for (const url of ["/", "/host.html"]) {
  test(`view switch preserves draft and exact review on ${url}`, async ({ page }) => {
    const api = new MockApi().waitingForApproval();
    await api.install(page);
    await page.goto(url);
    if (url !== "/") await page.getByTestId("overlay-launcher").click();
    await page.getByTestId("composer-input").fill("restock widget-a");
    await page.getByTestId("view-switch").selectOption("workbench");
    await expect(page.getByTestId("composer-input")).toHaveValue("restock widget-a");
    await expect(page.getByTestId("view-switch")).toBeFocused();
    await page.getByTestId("composer-submit").click();
    await expect(page.getByTestId("approval-approve")).toBeEnabled();
    await page.getByTestId("approval-approve").click();
    await expect(page.getByTestId("approval-confirm")).toBeVisible();
    await page.getByTestId("view-switch").selectOption("sidebar");
    await expect(page.getByTestId("approval-confirm")).toHaveCount(0);
    await expect(page.getByTestId("approval-approve")).toBeEnabled();
    await expect(page.getByTestId("material-field")).toHaveCount(3);
    await page.getByTestId("view-switch").selectOption("overlay");
    await expect(page.getByTestId("approval-approve")).toBeEnabled();
    if (url === "/") {
      await page.getByTestId("view-switch").selectOption("full-page");
      await expect(page.getByTestId("approval-approve")).toBeEnabled();
    } else {
      expect(await page.getByTestId("view-switch").locator('option[value="full-page"]').count()).toBe(0);
    }
    expect(api.createRuns).toBe(1);
    expect(api.decisions).toHaveLength(0);
  });
}

test("preference survives reload; explicit host layout overrides it", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/");
  await page.getByTestId("view-switch").selectOption("sidebar");
  await page.reload();
  await expect(page.getByTestId("view-switch")).toHaveValue("sidebar");
  await page.goto("/?layout=full-page");
  await expect(page.getByTestId("view-switch")).toHaveValue("full-page");
});

test("minimize retains draft; Escape backs out of confirm before minimizing", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/?layout=workbench");
  await page.getByTestId("overlay-launcher").click();
  await page.getByTestId("composer-input").fill("restock");
  await page.getByTestId("overlay-launcher").click();
  await expect(page.getByTestId("overlay-launcher")).toBeFocused();
  await page.getByTestId("overlay-launcher").click();
  await expect(page.getByTestId("composer-input")).toHaveValue("restock");
  await page.getByTestId("composer-submit").click();
  await page.getByTestId("approval-approve").click();
  await page.getByTestId("approval-confirm-prompt").press("Escape");
  await expect(page.getByTestId("approval-confirm")).toHaveCount(0);
  await page.getByTestId("approval-approve").press("Escape");
  await expect(page.getByTestId("overlay-panel")).toHaveCount(0);
  await expect(page.getByTestId("overlay-launcher")).toContainText("Review needed");
  expect(api.decisions).toHaveLength(0);
});

test("workbench adapts to a narrow viewport without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await new MockApi().waitingForApproval().install(page);
  await page.goto("/?layout=workbench");
  await page.getByTestId("overlay-launcher").click();
  await page.getByTestId("composer-input").fill("restock");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await page.getByTestId("approval-approve").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("approval-approve")).toBeInViewport();
  expect(
    await page.getByTestId("overlay-panel").evaluate(el => el.scrollWidth - el.clientWidth),
  ).toBeLessThanOrEqual(1);
});
