import { choosePreference } from "../src/preferences.ts";
/** Opt-in screenshots of real fixture review while switching presentation. */
import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const destination = process.env["E_AGENT_OVERLAY_CAPTURE_DIR"];
test("capture selectable enterprise agent surfaces", async ({ page }) => {
  test.skip(!destination, "Set E_AGENT_OVERLAY_CAPTURE_DIR to an unused directory");
  const dir = resolve(destination!);
  await mkdir(dir, { recursive: false });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/");
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  for (const mode of ["workbench", "overlay", "sidebar", "full-page"]) {
    await page.getByTestId("view-switch").selectOption(mode);
    await page.getByTestId("approval-approve").scrollIntoViewIfNeeded();
    await page.screenshot({ path: resolve(dir, `${mode}-review.png`), fullPage: true });
  }
  await page.getByTestId("view-switch").selectOption("workbench");
  await choosePreference(page, "theme", "dark");
  await page.screenshot({ path: resolve(dir, "workbench-dark.png") });
  await choosePreference(page, "theme", "light");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByTestId("approval-approve").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(dir, "workbench-mobile.png") });
});
