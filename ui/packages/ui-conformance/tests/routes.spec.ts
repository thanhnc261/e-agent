/**
 * Standalone navigation (enterprise overlay adoption plan FE-04). Navigating is a
 * presentation change: it starts no run, sends no command, keeps the draft and the
 * active run, and can never move a pending decision out of reach.
 */
import { expect, test } from "@playwright/test";
import { MockApi, RUN_ID } from "../src/index.ts";

test("moving between sections issues no run or command and keeps the draft", async ({ page }) => {
  const api = new MockApi();
  await api.install(page);
  const requests: string[] = [];
  page.on("request", request => {
    if (request.url().includes("/v1/"))
      requests.push(`${request.method()} ${new URL(request.url()).pathname}`);
  });
  await page.goto("/");
  await expect(page.getByTestId("page-overview")).toBeVisible();
  await page.getByTestId("composer-input").fill("draft that must survive");
  const before = requests.length;

  await page.getByTestId("section-connections").click();
  await expect(page.getByTestId("page-connections")).toBeVisible();
  await page.getByTestId("section-overview").click();
  await expect(page.getByTestId("page-overview")).toBeVisible();

  // Discovery projections are read when a section first needs them; nothing else.
  expect(requests.slice(before).filter(r => !r.startsWith("GET /v1/me/"))).toEqual([]);
  expect(api.createRuns).toBe(0);
  await expect(page.getByTestId("composer-input")).toHaveValue("draft that must survive");
});

test("Back returns to the previous section and keeps focus usable", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/");
  await page.getByTestId("section-connections").click();
  await expect(page.getByTestId("page-connections")).toBeVisible();
  await page.goBack();
  await expect(page.getByTestId("page-overview")).toBeVisible();
  await page.getByTestId("section-connections").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("page-connections")).toBeVisible();
});

test("an unknown route falls back to the overview", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/#/administration");
  await expect(page.getByTestId("page-overview")).toBeVisible();
});

test("a pending decision cannot be displaced by navigating to another section", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();

  await page.getByTestId("section-overview").click();
  // The route changed, but the surface still shows the decision and its terms.
  await expect(page.getByTestId("page-overview")).toHaveCount(0);
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await expect(page.getByTestId("material-field")).toHaveCount(3);
  expect(api.decisions).toHaveLength(0);
});

test("recent tasks show last-known state and re-read a task before a decision", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await page.getByTestId("approval-reject").click();
  await expect(page.getByTestId("approval-rejected")).toBeAttached();

  const item = page.getByTestId("history-task").first();
  // The sidebar shows the state last seen in this session; opening re-reads it.
  await expect(item).toContainText("restock");
  const reads = api.snapshotReads;
  await page.getByTestId("new-task").click();
  await page.getByTestId("history-task").first().click();
  await expect(page.getByTestId("run-task")).toHaveText("restock");
  expect(api.snapshotReads).toBeGreaterThan(reads);
  expect(api.createRuns).toBe(1);
});

test("the standalone sections and the review fit 320 CSS pixels", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.setViewportSize({ width: 320, height: 740 });
  const noOverflow = async () =>
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(
      0,
    );

  await page.goto("/");
  await expect(page.getByTestId("page-overview")).toBeVisible();
  await noOverflow();
  await page.getByTestId("section-connections").click();
  await expect(page.getByTestId("connections")).toBeVisible();
  await noOverflow();
  await page.getByTestId("section-overview").click();

  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await noOverflow();
  // The sticky decision controls must not cover the terms they belong to.
  await page.getByTestId("material-field").last().scrollIntoViewIfNeeded();
  await expect(page.getByTestId("material-field").last()).toBeInViewport();
  await page.getByTestId("approval-approve").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("approval-approve")).toBeInViewport();
  await noOverflow();
});

test("the standalone sections and the task surface work in Vietnamese", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/?lang=vi");
  await expect(page.getByTestId("section-overview")).toHaveText("Tổng quan");
  await expect(page.getByTestId("section-connections")).toHaveText("Khả năng");
  await page.getByTestId("section-connections").click();
  await expect(page.getByTestId("connections")).toContainText("Chỉ xem");
  await expect(page.getByTestId("connection-health").first()).toContainText("Chưa rõ");
  await expect(page.getByTestId("task-catalog")).toContainText("Sẵn sàng");
  await page.getByTestId("section-overview").click();

  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  // Exact canonical values stay verbatim in every locale.
  await expect(page.locator('[data-testid="material-field"][data-path="supplier_ref"]')).toContainText(
    "supplier:approved-co",
  );
  expect(await page.locator("html").getAttribute("lang")).toBe("vi");
});

test("a denied task route reports it once and offers a way out", async ({ page }) => {
  const api = new MockApi();
  await api.install(page);
  // FORBIDDEN is returned as 404 so a run outside scope is indistinguishable
  // from a missing one; both must stop, not retry.
  await page.route("**/v1/runs/other-principal-run", route =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ code: "FORBIDDEN", message: "not found" }),
    }),
  );
  let reads = 0;
  page.on("request", request => {
    if (new URL(request.url()).pathname === "/v1/runs/other-principal-run") reads += 1;
  });

  await page.goto("/#/task/other-principal-run");
  await expect(page.getByTestId("task-unavailable")).toBeVisible();
  await page.waitForTimeout(400);
  expect(reads).toBeLessThanOrEqual(2);
  // The address is kept, so the state explains itself instead of silently bouncing.
  expect(new URL(page.url()).hash).toBe("#/task/other-principal-run");

  await page.getByTestId("task-unavailable-overview").click();
  await expect(page.getByTestId("page-overview")).toBeVisible();
});

test("Back and Forward over an unavailable task cause no repeated reads", async ({ page }) => {
  const api = new MockApi();
  await api.install(page);
  let reads = 0;
  page.on("request", request => {
    if (new URL(request.url()).pathname === "/v1/runs/missing-task") reads += 1;
  });
  await page.goto("/");
  await page.getByTestId("section-connections").click();
  await page.evaluate(() => {
    location.hash = "#/task/missing-task";
  });
  await expect(page.getByTestId("task-unavailable")).toBeVisible();
  const afterFirst = reads;
  expect(afterFirst).toBeLessThanOrEqual(2);

  await page.goBack();
  await expect(page.getByTestId("page-connections")).toBeVisible();
  await page.goForward();
  await expect(page.getByTestId("task-unavailable")).toBeVisible();
  await page.waitForTimeout(300);
  // One deliberate navigation back to the address is one more attempt, not a loop.
  expect(reads).toBeLessThanOrEqual(afterFirst + 2);
  expect(api.createRuns).toBe(0);
});

test("choosing another task from history is not undone by the previous address", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await expect(page).toHaveURL(new RegExp(`#/task/${RUN_ID}$`));

  // Leave the task, then return to it through session history while the address
  // still names it: the controller leads and the address follows.
  await page.getByTestId("new-task").click();
  await expect(page.getByTestId("page-overview")).toBeVisible();
  expect(new URL(page.url()).hash).toBe("#/overview");

  await page.getByTestId("history-task").first().click();
  await expect(page.getByTestId("run-task")).toHaveText("restock");
  await expect(page).toHaveURL(new RegExp(`#/task/${RUN_ID}$`));
  expect(api.createRuns).toBe(1);
  expect(api.decisions).toHaveLength(0);
});
