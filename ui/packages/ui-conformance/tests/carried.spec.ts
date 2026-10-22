/**
 * The earlier runs a run used as hints (G-D 4.U1, brief item 8, ADR 0023 §6, AG-EXPL-2). Every
 * spec runs against the conformance mock with `features.conversations: on`; what is listed
 * comes only from the bundle's `conversation` section, built as the server builds it.
 */
import { expect, test, type Page } from "@playwright/test";
import { EARLIER_RUN_ID, MockApi, RUN_ID, runAxe } from "../src/index.ts";

function laterRun(mode: "on" | "shadow"): MockApi {
  const api = new MockApi();
  api.features = "on";
  api.twoRunThread();
  api.carryContext([EARLIER_RUN_ID], mode, RUN_ID);
  api.finish(RUN_ID, "Draft order PO-SAMPLE-1 (sample).");
  return api;
}

/** Open the conversation from the sidebar, then the later run's Sources tab. */
async function openSources(page: Page, api: MockApi): Promise<void> {
  await api.install(page);
  await page.goto("/");
  const row = page.getByTestId("thread-row").first();
  await row.waitFor({ state: "attached" });
  if (!(await row.isVisible())) await page.getByTestId("thread-list-toggle").click();
  await row.click();
  const workspace = page.getByTestId("artifact-workspace");
  // It opened by itself for the later run's result (G-B 6).
  await expect(workspace).toHaveAttribute("data-run-id", RUN_ID);
  await workspace.getByTestId("workspace-tab-sources").click();
  // The Sources tab reads the bundle once; wait until it is in the page.
  await expect(workspace.getByTestId("evidence-bundle")).toBeAttached();
}

test("a later run in on lists the earlier run as a hint, and selecting it opens that run", async ({
  page,
}) => {
  const api = laterRun("on");
  await openSources(page, api);
  const workspace = page.getByTestId("artifact-workspace");
  const carried = workspace.getByTestId("carried-runs");
  await expect(carried).toBeVisible();
  await expect(carried.getByRole("heading")).toHaveText("Used earlier runs as hints");
  const item = carried.getByTestId("carried-run");
  await expect(item).toHaveCount(1);
  // Named as the thread names it: its place and its task.
  await expect(item).toHaveText("Run 1 · which products are short?");
  await expect(item).toHaveAttribute("data-run-id", EARLIER_RUN_ID);
  // Hints, never evidence, never verified.
  expect((await carried.innerText()).toLowerCase()).not.toMatch(/verif|evidence/);
  expect(api.evidenceReads).toBe(1);

  // Activating it selects that run, as its run card does: the workspace shows the earlier
  // run, with focus on its heading.
  await item.focus();
  await page.keyboard.press("Enter");
  await expect(workspace).toHaveAttribute("data-run-id", EARLIER_RUN_ID);
  await expect(page.getByTestId("workspace-heading")).toHaveText("which products are short?");
  await expect(page.getByTestId("workspace-heading")).toBeFocused();
  // Closing returns focus to that run's card.
  await page.getByTestId("workspace-close").click();
  await expect(workspace).toHaveCount(0);
  await expect(page.getByTestId("thread-run").nth(0).getByTestId("run-card-open")).toBeFocused();
  // Selecting a run decided, sent and started nothing.
  expect(api.decisions).toHaveLength(0);
  expect(api.messages).toHaveLength(0);
  expect(api.messageStarts).toBe(0);
});

test("a later run in shadow lists nothing, since nothing reached the model", async ({ page }) => {
  const api = laterRun("shadow");
  await openSources(page, api);
  await expect(page.getByTestId("carried-runs")).toHaveCount(0);
  expect(api.evidenceReads).toBe(1);
});

test('axe: thread state "earlier runs used as hints" has no WCAG 2.2 AA violation', async ({ page }) => {
  await openSources(page, laterRun("on"));
  await expect(page.getByTestId("carried-runs")).toBeVisible();
  const result = await runAxe(page);
  // The count is printed so a run shows how many rules it checked (PR-31).
  console.log(
    `axe earlier runs used as hints: ${result.rules} rules, ${result.violations.length} violations`,
  );
  expect(result.rules, "axe ran no rule").toBeGreaterThan(0);
  expect(result.violations).toEqual([]);
});
