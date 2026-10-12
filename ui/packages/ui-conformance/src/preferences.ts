import type { Page } from "@playwright/test";

/** Exercise the visible preferences UI; close it before inspecting the task. */
export async function choosePreference(page: Page, dimension: string, value: string) {
  const trigger = page.getByTestId("preferences-toggle");
  await trigger.click();
  await page.getByTestId(`${dimension}-switch`).selectOption(value);
  await trigger.press("Escape");
}
