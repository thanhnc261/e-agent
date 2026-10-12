import { choosePreference } from "../src/preferences.ts";
/**
 * Presentation dimensions (enterprise overlay adoption plan §4). Theme, appearance
 * and density are independent of each other and of the surface, a host-pinned value
 * is authoritative and not offered as a choice, and none of them can change the
 * task, the review or what may be approved.
 */
import { expect, test } from "@playwright/test";
import { MockApi } from "../src/index.ts";

test("density is independent of theme and survives a surface change", async ({ page }) => {
  await page.goto("/");
  await choosePreference(page, "density", "compact");
  await choosePreference(page, "theme", "dark");
  const root = page.locator("html");
  await expect(root).toHaveAttribute("data-density", "compact");
  await expect(root).toHaveAttribute("data-theme", "dark");
  await expect(root).toHaveAttribute("data-appearance", "calm");

  // The compact token block must actually apply on top of the dark theme.
  const height = await page
    .getByTestId("composer-submit")
    .evaluate(node => Number.parseFloat(getComputedStyle(node).minHeight));
  expect(height).toBeGreaterThanOrEqual(24);
  expect(height).toBeLessThan(44);

  await page.getByTestId("view-switch").selectOption("sidebar");
  await expect(root).toHaveAttribute("data-density", "compact");
  await expect(root).toHaveAttribute("data-theme", "dark");
});

test("a preference survives reload; an explicit host value pins the dimension", async ({ page }) => {
  await page.goto("/");
  await choosePreference(page, "theme", "high-contrast");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "high-contrast");

  await page.goto("/?theme=dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  // A pinned dimension is authoritative, so no control offers to change it.
  await expect(page.getByTestId("theme-switch")).toHaveCount(0);
  await expect(page.getByTestId("density-switch")).toHaveCount(1);
});

test("changing presentation never changes the reviewable terms or the decision", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  const before = await page.getByTestId("material-field").allInnerTexts();

  await choosePreference(page, "theme", "dark");
  await choosePreference(page, "density", "compact");
  expect(await page.getByTestId("material-field").allInnerTexts()).toEqual(before);
  await expect(page.getByTestId("approval")).toHaveAttribute("data-phase", "reviewing");
  expect(api.decisions).toHaveLength(0);
});

test("an appearance changes emphasis only, never terms, status or interaction", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();

  const read = async () => ({
    fields: await page.getByTestId("material-field").allInnerTexts(),
    status: await page.getByTestId("run-state").innerText(),
    checks: await page.getByTestId("finding").allInnerTexts(),
    controls: await page.getByTestId("approval").locator("button").allInnerTexts(),
  });
  const calm = await read();

  for (const appearance of ["presence", "operator"]) {
    await choosePreference(page, "appearance", appearance);
    await expect(page.locator("html")).toHaveAttribute("data-appearance", appearance);
    expect(await read(), appearance).toEqual(calm);
    // Reaching the decision still takes exactly one step, and the terms stay legible.
    const terms = page.getByTestId("material-field").first();
    await expect(terms).toBeVisible();
    const covering = await terms.evaluate(node => {
      const box = node.getBoundingClientRect();
      const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return top === null || !node.contains(top);
    });
    expect(covering, `${appearance} must not obscure the terms`).toBe(false);
  }
  expect(api.decisions).toHaveLength(0);
});

test("reduced motion removes animation in every appearance", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  for (const appearance of ["calm", "presence", "operator"]) {
    await choosePreference(page, "appearance", appearance);
    const durations = await page.evaluate(() =>
      [...document.querySelectorAll(".ea-button, .ea-surface, .ea-panel")].flatMap(node => {
        const style = getComputedStyle(node);
        return [style.transitionDuration, style.animationDuration];
      }),
    );
    expect(
      durations.every(d => /^(0s|0ms)(,\s*(0s|0ms))*$/.test(d)),
      appearance,
    ).toBe(true);
  }
});
