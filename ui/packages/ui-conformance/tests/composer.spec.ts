/**
 * The composer carries the task's live status and its tools (owner review 2026-10-12).
 * Status sits with the task, not in the page header, and the Context panel shows only
 * what the request actually carries.
 */
import { expect, test } from "@playwright/test";
import { MockApi } from "../src/mock-api.ts";

test("the task status and Stop sit above the composer, not in the header", async ({ page }) => {
  await new MockApi().waitingForApproval().install(page);
  await page.goto("/");
  await expect(page.getByTestId("run-state")).toHaveCount(0);
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  const composer = page.getByTestId("composer");
  await expect(composer.getByTestId("run-state")).toContainText("Needs review");
  await expect(composer.getByTestId("run-state")).toHaveAttribute("role", "status");
  await expect(composer.getByTestId("run-cancel")).toBeVisible();
  await expect(page.locator(".ea-header [data-testid=run-state]")).toHaveCount(0);
});

test("the standalone workspace says it sends no page context", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/");
  await page.getByTestId("context-toggle").click();
  await expect(page.getByTestId("context-panel")).toBeVisible();
  await expect(page.getByTestId("context-none")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("context-panel")).not.toBeVisible();
  await expect(page.getByTestId("context-toggle")).toBeFocused();
});

test("an embedded surface shows the context it will send", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/host.html");
  await page.getByTestId("overlay-launcher").click();
  await page.getByTestId("context-toggle").click();
  const panel = page.getByTestId("context-panel");
  await expect(panel).toContainText("Embedded in another page");
  await expect(panel).toContainText(new URL(page.url()).origin);
  await expect(page.getByTestId("context-none")).toHaveCount(0);
});
