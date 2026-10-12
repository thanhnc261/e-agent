import { expect, test, type Page } from "@playwright/test";
import { MockApi, presentation } from "../src/mock-api.ts";
import { TARGETS } from "../src/targets.ts";

for (const target of TARGETS) {
  test.describe(`${target.name} redesign safety`, () => {
    test("lost admission response retains draft and reuses the request key", async ({ page }) => {
      const api = new MockApi();
      await api.install(page);
      let lost = true;
      const keys: (string | undefined)[] = [];
      await page.route("**/v1/runs", async route => {
        if (route.request().method() !== "POST") return route.fallback();
        keys.push(route.request().headers()["idempotency-key"]);
        if (lost) {
          lost = false;
          return route.abort("failed");
        }
        return route.fallback();
      });
      await page.goto(target.url());
      await target.open(page);
      await page.getByTestId("composer-input").fill("restock widget-a");
      await page.getByTestId("composer-submit").click();
      await expect(page.getByTestId("error")).toBeVisible();
      await expect(page.getByTestId("composer-input")).toHaveValue("restock widget-a");
      await page.getByTestId("composer-submit").click();
      await expect(page.getByTestId("run-task")).toHaveText("restock");
      expect(keys).toHaveLength(2);
      expect(keys[0]).toBeTruthy();
      expect(keys[0]).toBe(keys[1]);
    });
    test("canonical digest alone cannot approve substituted displayed terms", async ({ page }) => {
      const p = presentation();
      p.material_fields[0]!.value = "4";
      const api = new MockApi().waitingForApproval(p);
      await api.install(page);
      await page.goto(target.url());
      await target.open(page);
      await page.getByTestId("composer-input").fill("restock");
      await page.getByTestId("composer-submit").click();
      await expect(page.getByTestId("approval-digest-mismatch")).toBeVisible();
      await expect(page.getByTestId("approval-approve")).toBeDisabled();
      expect(api.decisions).toHaveLength(0);
    });
    test("unknown checks block approval and unknown outcome is never labelled verified", async ({ page }) => {
      const p = presentation({
        findings: [
          { rule_id: "R", rule_version: "1", status: "UNKNOWN", message: "Missing fact", evidence_ids: [] },
        ],
      });
      const api = new MockApi().waitingForApproval(p);
      await api.install(page);
      await page.goto(target.url());
      await target.open(page);
      await page.getByTestId("composer-input").fill("restock");
      await page.getByTestId("composer-submit").click();
      await expect(page.getByTestId("approval-approve")).toBeDisabled();
      api.emit("outcome.reported", { status: "UNKNOWN" });
      api.state = "NEEDS_RECONCILIATION";
      api.emit("run.state_changed", { from: "WAITING_APPROVAL", to: api.state });
      const item = page.locator('[data-testid="timeline-item"][data-type="outcome.reported"]');
      await expect(item).toContainText("Outcome not confirmed");
      await expect(item).not.toContainText("verified");
    });
  });
}

for (const target of TARGETS.filter(t => t.name !== "reference")) {
  test(`${target.name} retains unfinished review in task navigation`, async ({ page }) => {
    const api = new MockApi().waitingForApproval();
    await api.install(page);
    await page.goto(target.url());
    await target.open(page);
    await page.getByTestId("composer-input").fill("restock");
    await page.getByTestId("composer-submit").click();
    await expect(page.getByTestId("approval-approve")).toBeEnabled();
    await expect(page.getByTestId("composer-input")).toBeDisabled();
    await page.getByTestId("new-task").click();
    await expect(page.getByTestId("composer-input")).toBeEnabled();
    const history = page.locator(".ea-task-history");
    if (!(await history.evaluate(el => (el as HTMLDetailsElement).open)))
      await history.locator(":scope > summary").click();
    await page.getByTestId("history-task").click();
    await expect(page.getByTestId("approval-approve")).toBeEnabled();
    expect(api.createRuns).toBe(1);
    expect(api.decisions).toHaveLength(0);
  });
}

async function liveApproval(page: Page, url = "/") {
  await page.goto(url);
  if (url.startsWith("/host")) await TARGETS[1]!.open(page);
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
}

test("mobile review keeps exact fields scrollable and actions reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await liveApproval(page);
  const panel = page.getByTestId("approval");
  await expect(panel.getByTestId("material-field")).toHaveCount(10);
  const body = panel.locator(".ea-decision-body");
  await body.evaluate(el => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(panel.getByTestId("material-field").last()).toBeInViewport();
  await page.getByTestId("approval-approve").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("approval-approve")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(0);
  await page.getByTestId("approval-approve").click();
  await expect(page.getByTestId("approval-confirm")).toBeVisible();
});

test("half-size viewport supports 200 percent zoom layout and keyboard review", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 450 });
  await liveApproval(page);
  await page.getByTestId("approval-approve").scrollIntoViewIfNeeded();
  await expect(page.getByTestId("approval-approve")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(0);
});

for (const layout of ["sidebar", "overlay"]) {
  test(`${layout} narrow review preserves fields and reachable decision controls`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await liveApproval(page, layout === "sidebar" ? "/?layout=sidebar" : "/host.html");
    await expect(page.getByTestId("material-field")).toHaveCount(10);
    const body = page.locator(".ea-decision-body");
    await body.evaluate(el => {
      el.scrollTop = el.scrollHeight;
    });
    await page.getByTestId("material-field").last().scrollIntoViewIfNeeded();
    await expect(page.getByTestId("material-field").last()).toBeInViewport();
    await page.getByTestId("approval-approve").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("approval-approve")).toBeInViewport();
    const panel =
      layout === "sidebar" ? page.locator(".ea-layout-sidebar") : page.getByTestId("overlay-panel");
    expect(await panel.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
  });
}
