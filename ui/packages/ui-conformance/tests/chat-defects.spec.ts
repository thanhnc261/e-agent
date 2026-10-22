/**
 * Chat defects UX review (docs/reviews/2026-10-20-chat-defects-ux-review.md), owner G-0
 * 2026-10-20: the layout findings, checked at the widths and text size the review measured.
 */
import { expect, test, type Page } from "@playwright/test";
import { MockApi } from "../src/mock-api.ts";

async function inTask(page: Page) {
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
  await expect(page.getByTestId("pending-reply")).toContainText("Hello again! What next?");
}

async function welcome(page: Page) {
  await new MockApi().install(page);
  await page.goto("/");
  await expect(page.getByTestId("composer-input")).toBeVisible();
}

const horizontalOverflow = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

test("F-1 the conversation keeps a readable column at 200 % text", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await inTask(page);
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "200%";
  });
  const conversation = await page.locator(".ea-conversation").boundingBox();
  const body = await page.getByTestId("pending-reply").boundingBox();
  const inspector = await page.locator(".ea-inspector").boundingBox();
  expect(conversation && body && inspector).toBeTruthy();
  // At 200 % a 20rem line is 640 px; the thread keeps at least that, never 0 px.
  expect(conversation!.width).toBeGreaterThanOrEqual(640);
  // The short reply sits on one line, not one character per line (the defect: 0 px wide).
  const lines = await page
    .getByTestId("pending-reply")
    .evaluate(el => el.getBoundingClientRect().height / parseFloat(getComputedStyle(el).lineHeight));
  expect(body!.width).toBeGreaterThan(0);
  expect(lines).toBeLessThan(2);
  // Activity and Evidence never sit on top of the thread.
  const overlaps =
    inspector!.x < conversation!.x + conversation!.width &&
    conversation!.x < inspector!.x + inspector!.width &&
    inspector!.y < conversation!.y + conversation!.height &&
    conversation!.y < inspector!.y + inspector!.height;
  expect(overlaps).toBe(false);
  expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
});

for (const width of [320, 390]) {
  for (const [name, open] of [
    ["welcome", welcome],
    ["in a task", inTask],
  ] as const) {
    test(`F-2 the Context panel text stays visible at ${width} px (${name})`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 320 ? 720 : 844 });
      await open(page);
      await page.getByTestId("context-toggle").click();
      await expect(page.getByTestId("context-none")).toBeVisible();
      await expect(page.getByTestId("context-sent")).toBeVisible();
      const box = await page.getByTestId("context-none").boundingBox();
      expect(box?.height ?? 0).toBeGreaterThan(0);
    });

    test(`F-3 the open Context panel fits the viewport at ${width} px (${name})`, async ({ page }) => {
      await page.setViewportSize({ width, height: width === 320 ? 720 : 844 });
      await open(page);
      await page.getByTestId("context-toggle").click();
      const panel = await page.getByTestId("context-panel").boundingBox();
      expect(panel).toBeTruthy();
      expect(panel!.x).toBeGreaterThanOrEqual(0);
      expect(panel!.x + panel!.width).toBeLessThanOrEqual(width);
      expect(await horizontalOverflow(page)).toBeLessThanOrEqual(0);
    });
  }
}
