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

async function twoReplies(page: import("@playwright/test").Page) {
  const api = new MockApi();
  api.emit("run.created", { task: "hi" });
  api.emit("input.requested", { question: "Hello! What next?", kind: "reply" });
  api.emit("input.received", { input: "hi" });
  api.emit("input.requested", { question: "Hello again! What next?", kind: "reply" });
  api.emit("run.state_changed", { from: "RUNNING", to: "WAITING_INPUT" });
  api.state = "WAITING_INPUT";
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("hi");
  await page.getByTestId("composer-submit").click();
}

test("reply label shows once after hi, hi", async ({ page }) => {
  await twoReplies(page);
  await expect(page.getByTestId("pending-reply")).toContainText("Hello again! What next?");
  await expect(page.getByTestId("reply-label")).toHaveCount(1);
  await expect(page.getByTestId("reply-label")).toHaveText("Reply · not a verified result");
});

test("a later reply keeps a quiet not-verified hint", async ({ page }) => {
  await twoReplies(page);
  const later = page.getByTestId("pending-reply");
  await expect(later).toContainText("Hello again! What next?");
  const hintId = await later.getAttribute("aria-describedby");
  expect(hintId).toBeTruthy();
  const hint = page.locator(`[id="${hintId}"]`);
  await expect(hint).toHaveText("Reply · not a verified result");
  await expect(hint).toHaveClass(/ea-visually-hidden/);
});
