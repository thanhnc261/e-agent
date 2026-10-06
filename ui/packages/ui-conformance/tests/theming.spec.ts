/** Theming and embedding gates (UI architecture §8): same components, swapped tokens. */
import { expect, test } from "@playwright/test";
import { MockApi } from "../src/mock-api.ts";

test("theme swap changes appearance with no component change", async ({ page }) => {
  await new MockApi().install(page);
  const colors: Record<string, string> = {};
  for (const theme of ["light", "dark", "high-contrast"]) {
    await page.goto(`/?theme=${theme}`);
    const panel = page.getByTestId("approval");
    await panel.waitFor();
    colors[theme] = await panel.evaluate((el) => `${getComputedStyle(el).backgroundColor}|${getComputedStyle(el).color}`);
  }
  expect(new Set(Object.values(colors)).size).toBe(3);
});

test("overlay is isolated from hostile host-page CSS and follows its theme attribute", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/host.html");
  const launcher = page.getByTestId("overlay-launcher");
  await launcher.click();
  const panel = page.getByTestId("overlay-panel");
  const style = await panel.evaluate((el) => {
    const s = getComputedStyle(el);
    return { font: s.fontFamily, color: s.color, spacing: s.letterSpacing };
  });
  expect(style.font).not.toContain("Comic Sans");
  expect(style.color).not.toBe("rgb(255, 0, 255)");
  expect(style.spacing).toBe("normal");
  const light = await panel.evaluate((el) => getComputedStyle(el).backgroundColor);
  await page.evaluate(() => document.getElementById("agent")?.setAttribute("theme", "dark"));
  await expect.poll(() => panel.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe(light);
});
