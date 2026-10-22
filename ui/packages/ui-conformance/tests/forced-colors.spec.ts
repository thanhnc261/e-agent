/** Forced colours (EA-14): selection, boundaries and the decision stay visible without author colours. */
import { expect, test } from "@playwright/test";
import { MockApi, tenFieldPresentation } from "../src/mock-api.ts";

test("forced colours keep the current section, controls and decision visible", async ({ page }) => {
  await page.emulateMedia({ forcedColors: "active" });
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/");
  const current = page.locator('.ea-section-link[aria-current="page"]');
  await expect(current).toBeVisible();
  expect(await current.evaluate(node => getComputedStyle(node).outlineStyle)).toBe("solid");

  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  const approve = page.getByTestId("approval-approve");
  await expect(approve).toBeEnabled();
  for (const control of [approve, page.getByTestId("approval-reject"), page.getByTestId("run-state")]) {
    const width = await control.evaluate(node => parseFloat(getComputedStyle(node).borderTopWidth));
    expect(width).toBeGreaterThanOrEqual(1);
  }
  // Keyboard focus, so the focus-visible style applies as it would for a user.
  await page.getByTestId("approval-reject").focus();
  await page.keyboard.press("Shift+Tab");
  await expect(approve).toBeFocused();
  expect(await approve.evaluate(node => getComputedStyle(node).outlineStyle)).toBe("solid");
});

test("forced colours keep the workspace scroll cue, as a border, not a gradient", async ({ page }) => {
  await page.emulateMedia({ forcedColors: "active" });
  await page.setViewportSize({ width: 1280, height: 800 });
  const api = new MockApi();
  api.features = "on";
  api.twoRunThread();
  api.waitingForApproval(tenFieldPresentation());
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("thread-row").first().click();
  const workspace = page.getByTestId("artifact-workspace");
  await expect(workspace.getByTestId("approval-approve")).toBeEnabled();
  // G-D 4.U4: more is below, and the cue says so without author colours.
  const cue = workspace.getByTestId("workspace-scroll-cue");
  await expect(cue).toBeVisible();
  const style = await cue.evaluate(node => {
    const s = getComputedStyle(node);
    return { image: s.backgroundImage, border: s.borderTopStyle, width: parseFloat(s.borderTopWidth) };
  });
  expect(style.image).toBe("none");
  expect(style.border).toBe("dashed");
  expect(style.width).toBeGreaterThanOrEqual(1);
});

test("forced colours underline only the selected workspace tab", async ({ page }) => {
  await page.emulateMedia({ forcedColors: "active" });
  const api = new MockApi();
  api.features = "on";
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await page.goto("/");
  await page.getByTestId("thread-row").first().click();
  const workspace = page.getByTestId("artifact-workspace");
  await expect(workspace.getByTestId("approval-approve")).toBeEnabled();
  // EA-14, G-D 4.U7: the current tab is the one underlined; the others blend into Canvas.
  const canvas = await workspace.evaluate(node => getComputedStyle(node).backgroundColor);
  const underline = (id: string) =>
    workspace.getByTestId(id).evaluate(node => {
      const s = getComputedStyle(node);
      return { color: s.borderBottomColor, width: parseFloat(s.borderBottomWidth) };
    });
  const selected = await underline("workspace-tab-decision");
  await expect(workspace.getByTestId("workspace-tab-decision")).toHaveAttribute("aria-selected", "true");
  expect(selected.width).toBeGreaterThanOrEqual(2);
  expect(selected.color).not.toBe(canvas);
  let unselected = 0;
  for (const id of ["workspace-tab-sources", "workspace-tab-activity"]) {
    const tab = await underline(id);
    expect(tab.color, id).toBe(canvas);
    expect(tab.color).not.toBe(selected.color);
    unselected += 1;
  }
  expect(unselected).toBe(2);
  // Selecting another tab moves the underline with it.
  await workspace.getByTestId("workspace-tab-activity").click();
  expect((await underline("workspace-tab-activity")).color).not.toBe(canvas);
  expect((await underline("workspace-tab-decision")).color).toBe(canvas);
});
