/**
 * Conversation threads (Task 4e.4, ADR 0034 §1–§2, owner-selected mockup variant A1).
 * Every spec runs against the conformance mock with `features.conversations` set as named;
 * the thread is built from the mock's conversation snapshot and run events only.
 */
import { expect, test, type Page } from "@playwright/test";
import {
  CONVERSATION_ID,
  EARLIER_ANSWER,
  EARLIER_RUN_ID,
  HINT_BUSY,
  MockApi,
  RUN_ID,
  runAxe,
  tenFieldPresentation,
} from "../src/index.ts";

interface Surface {
  /** The ADR 0016 name the view switch shows. */
  name: string;
  url: string;
  open(page: Page): Promise<void>;
}

const launch = async (page: Page) => {
  const launcher = page.getByTestId("overlay-launcher");
  await launcher.waitFor();
  if ((await launcher.getAttribute("aria-expanded")) !== "true") await launcher.click();
};

/** The four surfaces of ADR 0016 (mockup self-review S-5). */
const SURFACES: Surface[] = [
  { name: "Workspace", url: "/", open: async () => {} },
  { name: "Docked", url: "/?layout=sidebar", open: async () => {} },
  { name: "Compact", url: "/host.html", open: launch },
  { name: "Workbench", url: "/?layout=workbench", open: launch },
];
const WORKSPACE = SURFACES[0] as Surface;

function onApi(): MockApi {
  const api = new MockApi();
  api.features = "on";
  return api;
}

/** Open the conversation from the sidebar, as a user would. */
async function openThread(page: Page, surface: Surface = WORKSPACE): Promise<void> {
  await page.goto(surface.url);
  await surface.open(page);
  const row = page.getByTestId("thread-row").first();
  // Wait for the server's list; narrow surfaces keep it in a closed disclosure.
  await row.waitFor({ state: "attached" });
  if (!(await row.isVisible())) await page.getByTestId("thread-list-toggle").click();
  await row.click();
  await expect(page.getByTestId("thread")).toBeVisible();
}

async function send(page: Page, text: string): Promise<void> {
  const input = page.getByTestId("composer-input");
  await input.fill(text);
  await input.press("Enter");
}

for (const surface of SURFACES) {
  test(`two runs show in one thread · ${surface.name}`, async ({ page }) => {
    const api = onApi();
    api.twoRunThread();
    api.waitingForApproval();
    await api.install(page);
    await openThread(page, surface);

    const runs = page.getByTestId("thread-run");
    await expect(runs).toHaveCount(2);
    // Oldest first, each with its own messages and its own compact card.
    await expect(runs.nth(0)).toHaveAttribute("data-run-id", EARLIER_RUN_ID);
    await expect(runs.nth(0)).toContainText("which products are short?");
    await expect(runs.nth(0)).toContainText(EARLIER_ANSWER);
    await expect(runs.nth(0).getByTestId("run-card-status")).toHaveText(/Completed · verified/);
    await expect(runs.nth(1)).toHaveAttribute("data-run-id", RUN_ID);
    await expect(runs.nth(1)).toContainText("draft a PO for it");
    await expect(runs.nth(1).getByTestId("run-card-status")).toHaveText(/Needs review/);
    // The agent's words are labelled on the message (G-B 5).
    await expect(runs.nth(0).getByTestId("agent-words-message")).toBeVisible();
    // One composer for the whole thread.
    await expect(page.getByTestId("composer")).toHaveCount(1);
    // The stream status is shown in the thread at every width (S-2, AG-STAT-3).
    await expect(page.getByTestId("thread-head").getByTestId("connection-status")).toBeVisible();
    // Opening a conversation sends nothing.
    expect(api.createRuns).toBe(0);
    expect(api.messageStarts).toBe(0);
    expect(api.messages).toHaveLength(0);
  });
}

test("the sidebar lists one thread", async ({ page }) => {
  const api = onApi();
  await api.install(page);
  await page.goto("/");
  await expect(page.getByTestId("thread-list")).toContainText("No conversations yet");

  await send(page, "which products are short?");
  await expect(page.getByTestId("thread-run")).toHaveCount(1);
  api.finish(RUN_ID, EARLIER_ANSWER);
  await expect(page.getByTestId("run-card-status")).toHaveText(/Completed · verified/);

  await send(page, "draft a PO for it");
  await expect(page.getByTestId("thread-run")).toHaveCount(2);
  const rows = page.getByTestId("thread-row");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("which products are short?");
  await expect(rows.first()).toHaveAttribute("aria-current", "page");
  // The row shows the latest run's state, as the server lists it.
  await expect(rows.first()).toContainText("Working on it");
  expect(api.messageStarts).toBe(2);
  expect(api.createRuns).toBe(0);
  expect(api.conversations.size).toBe(1);
});

test("the sidebar keeps legacy runs in a separate last-seen group", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/?layout=sidebar");
  await send(page, "restock");
  await expect(page.getByTestId("run-status")).toBeVisible();
  // The server turns conversations on; this session's earlier run stays outside them.
  api.features = "on";
  await page.reload();
  const legacy = page.getByTestId("legacy-group");
  if (!(await legacy.isVisible())) await page.getByTestId("thread-list-toggle").click();
  await expect(legacy).toContainText("Earlier tasks · this session · last seen");
  await expect(legacy.getByTestId("history-task")).toHaveCount(1);
  await expect(legacy.getByTestId("history-task")).toContainText("last seen");
  await expect(page.getByTestId("thread-row")).toHaveCount(0);
  // The legacy run opens as today's per-run view, marked as outside every conversation.
  await expect(page.getByTestId("legacy-note")).toContainText("not part of a conversation");
  await expect(page.getByTestId("thread")).toHaveCount(0);
});

test("a legacy run in on keeps today's composer lock while its approval waits", async ({ page }) => {
  const api = new MockApi().waitingForApproval();
  await api.install(page);
  await page.goto("/?layout=sidebar");
  await send(page, "restock");
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  api.features = "on";
  await page.reload();
  // The legacy run's per-run view: the decision waits, and the composer is locked as today,
  // so a send cannot start a conversation and move the view away from the approval.
  await expect(page.getByTestId("legacy-note")).toBeVisible();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await expect(page.getByTestId("composer-input")).toBeDisabled();
  await expect(page.getByTestId("composer-submit")).toBeDisabled();
  await expect(page.getByTestId("stop-slot")).toHaveCount(0);
  expect(api.messageStarts).toBe(0);
  expect(api.messages).toHaveLength(0);
  expect(api.createRuns).toBe(1);
});

test("the workspace closes and reopens, and the conversation stays", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await openThread(page);

  const workspace = page.getByTestId("artifact-workspace");
  // It opened by itself for the decision (G-B 6) and holds today's unchanged card.
  await expect(workspace).toBeVisible();
  await expect(workspace.getByTestId("approval-approve")).toBeEnabled();
  const card = await page.getByTestId("approval").innerText();
  await page.getByTestId("composer-input").fill("keep this draft");

  await page.getByTestId("workspace-close").click();
  await expect(workspace).toHaveCount(0);
  await expect(page.getByTestId("approval-approve")).toHaveCount(0);
  await expect(page.getByTestId("thread-run")).toHaveCount(2);
  await expect(page.getByTestId("composer-input")).toHaveValue("keep this draft");
  // With the workspace closed, the run card and the stop slot carry the status (A1).
  const latest = page.getByTestId("thread-run").nth(1);
  await expect(latest.getByTestId("run-card-status")).toHaveText(/Needs review/);
  await expect(page.getByTestId("stop-slot")).toContainText("Needs review");
  const open = latest.getByTestId("run-card-open");
  await expect(open).toHaveText(/Open the decision/);
  await expect(open).toBeFocused();

  await open.click();
  await expect(workspace).toBeVisible();
  await expect(page.getByTestId("workspace-heading")).toBeFocused();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await expect(page.getByTestId("material-field")).toHaveCount(3);
  expect(await page.getByTestId("approval").innerText()).toBe(card);

  // Escape backs out of the confirmation first, then closes; focus returns to Open.
  await page.getByTestId("approval-approve").click();
  await expect(page.getByTestId("approval-confirm")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("approval-confirm")).toHaveCount(0);
  await expect(workspace).toBeVisible();
  await page.getByTestId("approval-approve").press("Escape");
  await expect(workspace).toHaveCount(0);
  await expect(open).toBeFocused();
  await expect(page.getByTestId("composer-input")).toHaveValue("keep this draft");
  expect(api.decisions).toHaveLength(0);
});

test("Open the decision only opens: pressed while the decision is open, it brings the workspace forward", async ({
  page,
}) => {
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await openThread(page);
  const workspace = page.getByTestId("artifact-workspace");
  // It opened by itself for the decision (G-B 6), without moving focus.
  await expect(workspace).toHaveAttribute("data-run-id", RUN_ID);
  const open = page.getByTestId("thread-run").nth(1).getByTestId("run-card-open");
  await expect(open).toHaveText(/Open the decision/);
  // Not a toggle (G-D 4.U5): no expanded state, whatever the workspace shows.
  await expect(open).not.toHaveAttribute("aria-expanded");
  // Away from the decision tab, a press brings the decision forward with focus on the heading.
  await workspace.getByTestId("workspace-tab-activity").click();
  await open.click();
  await expect(workspace).toBeVisible();
  await expect(workspace.getByTestId("workspace-tab-decision")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId("workspace-heading")).toBeFocused();
  // Pressed again, it still never closes the workspace; closing stays with Close.
  await open.focus();
  await page.keyboard.press("Enter");
  await expect(workspace).toBeVisible();
  await expect(page.getByTestId("workspace-heading")).toBeFocused();
  await expect(workspace.getByTestId("approval-approve")).toBeEnabled();
  await page.getByTestId("workspace-close").click();
  await expect(workspace).toHaveCount(0);
  await expect(open).toBeFocused();
  expect(api.decisions).toHaveLength(0);
});

test("a workspace the user closed stays closed after a surface switch", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await openThread(page);
  const workspace = page.getByTestId("artifact-workspace");
  await expect(workspace).toBeVisible(); // opened by itself for the decision (G-B 6)
  await page.getByTestId("workspace-close").click();
  await expect(workspace).toHaveCount(0);

  // Both surfaces are wide enough to open it by itself; the user's close still holds (EA-10).
  await page.getByTestId("view-switch").selectOption("workbench");
  await expect(page.getByTestId("thread-run")).toHaveCount(2);
  await expect(workspace).toHaveCount(0);
  await page.getByTestId("view-switch").selectOption("full-page");
  await expect(page.getByTestId("thread-run")).toHaveCount(2);
  await expect(workspace).toHaveCount(0);
  // It reopens from the run card, with the decision unchanged.
  await page.getByTestId("thread-run").nth(1).getByTestId("run-card-open").click();
  await expect(workspace.getByTestId("approval-approve")).toBeEnabled();
  expect(api.decisions).toHaveLength(0);
});

test("the result carries the agent's-words label apart from what was checked", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.finish(RUN_ID, "Draft order PO-SAMPLE-1 (sample).");
  await api.install(page);
  await openThread(page);
  const workspace = page.getByTestId("artifact-workspace");
  await expect(workspace).toBeVisible(); // opened by itself for the result (G-B 6)
  await expect(workspace.getByTestId("workspace-tab-result")).toHaveAttribute("aria-selected", "true");
  // G-B 5: the agent's words are labelled on the result, beside the checked outcome.
  const words = workspace.getByTestId("agent-words-result");
  await expect(words).toContainText("The agent's words");
  await expect(words).toContainText("Written by e-agent. The result shows what was checked.");
  await expect(words).toContainText("Draft order PO-SAMPLE-1 (sample).");
  await expect(workspace.getByTestId("outcome")).toBeVisible();
});

test("a narrow workspace replaces the thread, and Back returns to the conversation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await openThread(page, SURFACES[1] as Surface);
  // On a narrow surface it does not open by itself: the card offers the decision.
  await expect(page.getByTestId("artifact-workspace")).toHaveCount(0);
  const open = page.getByTestId("thread-run").nth(1).getByTestId("run-card-open");
  await open.click();
  await expect(page.getByTestId("artifact-workspace")).toBeVisible();
  await expect(page.getByTestId("thread")).toBeHidden();
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await page.getByTestId("workspace-back").click();
  await expect(page.getByTestId("thread")).toBeVisible();
  await expect(open).toBeFocused();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

/** At 390 px in Docked, open the latest run's workspace from its card: a full view. */
async function narrowWorkspace(page: Page, api: MockApi): Promise<void> {
  await page.setViewportSize({ width: 390, height: 844 });
  await api.install(page);
  await openThread(page, SURFACES[1] as Surface);
  await page.getByTestId("thread-run").nth(1).getByTestId("run-card-open").click();
  await expect(page.getByTestId("artifact-workspace")).toBeVisible();
  await expect(page.getByTestId("thread")).toBeHidden();
}

test("a narrow workspace keeps Stop and the stream status in its head", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.state = "RUNNING";
  await narrowWorkspace(page, api);
  const workspace = page.getByTestId("artifact-workspace");
  // G-D 4.U2, AG-CTRL-1 and AG-STAT-3: the full view hides the thread, not Stop or the status.
  const slot = workspace.getByTestId("stop-slot");
  await expect(slot).toBeVisible();
  await expect(slot.getByTestId("stop")).toBeEnabled();
  // Compact: the head's own badge already names this run's status.
  await expect(slot.getByTestId("stop-slot-status")).toBeHidden();
  await expect(workspace.getByTestId("workspace-status")).toHaveText(/Working on it/);
  await expect(workspace.getByTestId("connection-status")).toBeVisible();
  await expect(workspace.getByTestId("connection-status")).toHaveText(/Connect|Reconnect|Up to date/);
  // Exactly one of each is shown: the thread's own are hidden with the thread.
  await expect(page.locator('[data-testid="stop"]:visible')).toHaveCount(1);
  await expect(page.locator('[data-testid="connection-status"]:visible')).toHaveCount(1);

  // The same rules as the thread's slot: disabled with its reason once nothing runs.
  api.finish(RUN_ID);
  await expect(slot.getByTestId("stop")).toBeDisabled();
  await expect(slot.getByTestId("stop-reason")).toHaveText("Nothing is running");
  // Back to the conversation, the thread's own slot carries it again.
  await page.getByTestId("workspace-back").click();
  await expect(page.getByTestId("artifact-workspace")).toHaveCount(0);
  await expect(page.locator('[data-testid="stop-slot"]:visible')).toHaveCount(1);
  await expect(page.getByTestId("thread-head").getByTestId("connection-status")).toBeVisible();
  expect(api.decisions).toHaveLength(0);
});

test("a narrow workspace offers the safe check, not Stop, while the result is unconfirmed", async ({
  page,
}) => {
  const api = onApi();
  api.twoRunThread();
  api.state = "NEEDS_RECONCILIATION";
  await narrowWorkspace(page, api);
  const slot = page.getByTestId("artifact-workspace").getByTestId("stop-slot");
  await expect(slot.getByTestId("stop")).toBeDisabled();
  await expect(slot.getByTestId("stop-reason")).toHaveText(
    "Stopping is unavailable while the result is unconfirmed",
  );
  await expect(slot.getByTestId("stop-reconcile")).toHaveText("Check operation status");
});

test("a wide workspace adds no second Stop or status: the thread beside it shows them", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await openThread(page);
  const workspace = page.getByTestId("artifact-workspace");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByTestId("stop-slot")).toHaveCount(0);
  await expect(workspace.getByTestId("connection-status")).toHaveCount(0);
  await expect(page.getByTestId("thread-head").getByTestId("connection-status")).toBeVisible();
});

test("a conversation opens at its latest run, with the composer in view, and focus stays", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await page.goto("/?layout=sidebar");
  const row = page.getByTestId("thread-row").first();
  await row.waitFor({ state: "attached" });
  if (!(await row.isVisible())) await page.getByTestId("thread-list-toggle").click();
  await row.click();
  const focused = await page.evaluateHandle(() => document.activeElement);
  await expect(page.getByTestId("thread-run")).toHaveCount(2);
  // G-D 4.U3 (AG-STAT-1, AG-ENT-3): the latest run's card, its status, and the composer.
  const latest = page.getByTestId("thread-run").nth(1).getByTestId("run-card");
  await expect(latest).toBeInViewport({ ratio: 1 });
  await expect(latest.getByTestId("run-card-status")).toHaveText(/Needs review/);
  await expect(page.getByTestId("composer")).toBeInViewport({ ratio: 1 });
  // The stream status stays in view too: the thread head is sticky in its scroller (GD-2,
  // AG-STAT-3), and covers no part of the latest card.
  const head = page.getByTestId("thread-head");
  await expect(head.getByTestId("connection-status")).toBeInViewport({ ratio: 1 });
  const headBox = await head.boundingBox();
  const cardBox = await latest.boundingBox();
  expect(headBox && cardBox && headBox.y + headBox.height <= cardBox.y + 1).toBe(true);
  // Scrolled, not focused (EA-16): focus is where the user's click left it.
  expect(await page.evaluate(el => document.activeElement === el, focused)).toBe(true);
  expect(api.messageStarts).toBe(0);
});

/**
 * Tab backwards from the composer through the thread's controls; each focused control must sit
 * at or below the sticky thread head (GR-1, WCAG 2.4.11). Before each Shift+Tab the thread is
 * scrolled so the control about to take focus lies under the head, as after a user's own
 * scroll: the browser then has to bring it out from under the head. Returns how many controls
 * were checked.
 */
async function focusNeverUnderHead(page: Page): Promise<number> {
  const targets = await page.evaluate(() => {
    const thread = document.querySelector('[data-testid="thread"]')!;
    const all = [...thread.querySelectorAll<HTMLElement>("button, a[href], [tabindex='0']")];
    all.forEach((el, i) => el.setAttribute("data-focus-probe", String(i)));
    return all.length;
  });
  let checked = 0;
  for (let i = targets - 1; i >= 0; i -= 1) {
    // Hide control i under the head, then focus the control after it without scrolling.
    await page.evaluate(index => {
      const target = document.querySelector<HTMLElement>(`[data-focus-probe="${index}"]`)!;
      const head = document.querySelector('[data-testid="thread-head"]')!;
      let scroller: HTMLElement | null = target.parentElement;
      while (scroller && !["auto", "scroll"].includes(getComputedStyle(scroller).overflowY))
        scroller = scroller.parentElement;
      const delta = target.getBoundingClientRect().top - head.getBoundingClientRect().top - 2;
      if (scroller) scroller.scrollTop += delta;
      else window.scrollBy(0, delta);
      const next =
        document.querySelector<HTMLElement>(`[data-focus-probe="${index + 1}"]`) ??
        document.querySelector<HTMLElement>('[data-testid="composer-input"]')!;
      next.focus({ preventScroll: true });
    }, i);
    await page.keyboard.press("Shift+Tab");
    const where = await page.evaluate(index => {
      const el = document.activeElement as HTMLElement;
      const head = document.querySelector('[data-testid="thread-head"]')!;
      return {
        same: el.getAttribute("data-focus-probe") === String(index),
        top: el.getBoundingClientRect().top,
        bottom: head.getBoundingClientRect().bottom,
        what: el.dataset["testid"] ?? el.tagName,
      };
    }, i);
    expect(where.same, `Shift+Tab reached control ${i}`).toBe(true);
    expect(where.top, `${where.what} (control ${i}) is under the head`).toBeGreaterThanOrEqual(
      where.bottom - 1,
    );
    checked += 1;
  }
  return checked;
}

for (const [name, viewport, surface] of [
  ["390 in Docked", { width: 390, height: 844 }, 1],
  ["1440 on the Workspace page", { width: 1440, height: 560 }, 0],
] as const) {
  test(`focus is never under the sticky thread head · ${name}`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize(viewport);
    const api = onApi();
    api.twoRunThread();
    // Four more earlier runs, so the earliest cards are far above the composer.
    for (let i = 1; i <= 4; i += 1) {
      const run = api.addRun({
        runId: `run-conformance-older-${i}`,
        task: `older question ${i} (sample)`,
        conversationId: CONVERSATION_ID,
        createdAt: `2026-10-04T0${i}:00:00Z`,
      });
      api.emit("run.created", { task: run.task }, run.runId);
      api.emit("run.state_changed", { from: "CREATED", to: "RUNNING" }, run.runId);
      api.finish(run.runId, `Older answer ${i} (sample).`);
    }
    api.state = "RUNNING";
    await api.install(page);
    await openThread(page, SURFACES[surface] as Surface);
    await expect(page.getByTestId("thread-run")).toHaveCount(6);
    // Tall enough to scroll, so a focused control could hide under the head.
    const scrolls = await page.evaluate(() => {
      const thread = document.querySelector('[data-testid="thread"]')!;
      for (let n: HTMLElement | null = thread.parentElement; n; n = n.parentElement) {
        const o = getComputedStyle(n).overflowY;
        if ((o === "auto" || o === "scroll") && n.scrollHeight > n.clientHeight) return true;
      }
      return document.documentElement.scrollHeight > innerHeight;
    });
    expect(scrolls).toBe(true);
    const checked = await focusNeverUnderHead(page);
    console.log(`focus under head (${name}): ${checked} controls checked`);
    expect(checked, "too few thread controls were focused").toBeGreaterThanOrEqual(6);
  });
}

test("a new run is scrolled into view once; a later update keeps the user's scroll", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 390, height: 844 });
  const api = onApi();
  api.twoRunThread();
  api.finish(RUN_ID, "Draft order PO-SAMPLE-1 (sample).");
  await api.install(page);
  await openThread(page, SURFACES[1] as Surface);
  await expect(page.getByTestId("thread-run").nth(1).getByTestId("run-card")).toBeInViewport({ ratio: 1 });
  await send(page, "and the next one");
  await expect(page.getByTestId("thread-run")).toHaveCount(3);
  const newest = page.getByTestId("thread-run").nth(2).getByTestId("run-card");
  await expect(newest).toBeInViewport({ ratio: 1 });
  await expect(page.getByTestId("composer-input")).toBeFocused();

  // The user scrolls back up; the same run's later change does not pull the view down.
  const scroller = page.locator(".ea-thread-stack");
  await scroller.evaluate(el => {
    el.scrollTop = 0;
  });
  api.finish(api.current, "Done (sample).");
  await expect(newest.getByTestId("run-card-status")).toHaveText(/Completed/);
  await page.waitForTimeout(300);
  expect(await scroller.evaluate(el => el.scrollTop)).toBe(0);
});

test("opened at its latest run in a surface that scrolls itself, the workspace head stays in view", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 844 });
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await openThread(page, SURFACES[3] as Surface);
  const workspace = page.getByTestId("artifact-workspace");
  await expect(workspace.getByTestId("approval-approve")).toBeEnabled();
  await expect(page.getByTestId("thread-run").nth(1).getByTestId("run-card")).toBeInViewport({ ratio: 1 });
  await expect(page.getByTestId("composer")).toBeInViewport({ ratio: 1 });
  // The side workspace fits the Workbench's own scroll region, so its head is not pushed out
  // at the end of the thread (G-D 4.U4 with 4.U3).
  for (const id of ["workspace-heading", "workspace-status", "workspace-close"]) {
    await expect(workspace.getByTestId(id)).toBeInViewport({ ratio: 1 });
    expect(await insideWorkspace(page, id), id).toBe(true);
  }
});

/** True when `testId` lies fully inside the workspace's visible box (not scrolled out of it). */
async function insideWorkspace(page: Page, testId: string): Promise<boolean> {
  return page.getByTestId("artifact-workspace").evaluate((aside, id) => {
    const el = aside.querySelector(`[data-testid="${id}"]`);
    if (!el) return false;
    const box = aside.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    return r.top >= box.top - 1 && r.bottom <= box.bottom + 1 && r.bottom <= innerHeight;
  }, testId);
}

test("a tall decision keeps the workspace head in view and shows that more is below", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval(tenFieldPresentation());
  await api.install(page);
  await openThread(page);
  const workspace = page.getByTestId("artifact-workspace");
  const approve = workspace.getByTestId("approval-approve");
  await expect(approve).toBeEnabled();
  await expect(workspace.getByTestId("material-field")).toHaveCount(10);
  // Let the bring-into-view of the new proposal settle.
  await page.waitForTimeout(400);
  // G-D 4.U4 (AG-STAT-1): the title, its status and Close stay in view on open.
  for (const id of ["workspace-heading", "workspace-status", "workspace-close"])
    expect(await insideWorkspace(page, id), id).toBe(true);
  // AG-APPR-3: Approve is below the fold, and the region says that more is below.
  expect(await insideWorkspace(page, "approval-approve")).toBe(false);
  const cue = workspace.getByTestId("workspace-scroll-cue");
  await expect(cue).toBeVisible();
  await expect(cue).toHaveAttribute("aria-hidden", "true");
  // Scrolled to the end: Approve is in view, the cue is gone and the head is still there.
  await workspace.evaluate(el => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(cue).toBeHidden();
  expect(await insideWorkspace(page, "approval-approve")).toBe(true);
  for (const id of ["workspace-heading", "workspace-status", "workspace-close"])
    expect(await insideWorkspace(page, id), id).toBe(true);
  // The head covers no term: a field brought into view lands below the sticky head, and the
  // card's top does too (scroll-padding and scroll-margin, G-D 4.U4).
  const below = async (testId: string, index: number) =>
    workspace.evaluate(
      (el, [id, i]) => {
        const head = el.querySelector(".ea-ws-head")!.getBoundingClientRect();
        const target = el.querySelectorAll(`[data-testid="${id}"]`)[i as number]!;
        target.scrollIntoView({ block: "start" });
        return target.getBoundingClientRect().top >= head.bottom - 1;
      },
      [testId, index] as const,
    );
  expect(await below("material-field", 4)).toBe(true);
  expect(await below("approval", 0)).toBe(true);
  await workspace.evaluate(el => {
    el.scrollTop = 0;
  });
  await expect(cue).toBeVisible();
  expect(api.decisions).toHaveLength(0);
});

test("a short decision shows no scroll cue", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  await api.install(page);
  await openThread(page);
  const workspace = page.getByTestId("artifact-workspace");
  await expect(workspace.getByTestId("approval-approve")).toBeEnabled();
  await page.waitForTimeout(400);
  expect(await insideWorkspace(page, "approval-approve")).toBe(true);
  await expect(workspace.getByTestId("workspace-scroll-cue")).toBeHidden();
});

test("a message during approval shows the hint, and the card is unchanged", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  api.refuseMessages = HINT_BUSY;
  await api.install(page);
  await openThread(page);
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  const card = await page.getByTestId("approval").innerText();

  const input = page.getByTestId("composer-input");
  // The composer stays open while the decision waits (G-B 4).
  await expect(input).toBeEnabled();
  await send(page, "also add 10 of hinge H-3");

  const refusal = page.getByTestId("composer").getByTestId("refusal");
  await expect(refusal).toContainText(
    "This conversation is busy. Wait, decide the approval, or stop the task.",
  );
  await expect(refusal).toContainText("Not sent · your text is kept");
  await expect(input).toHaveValue("also add 10 of hinge H-3");
  // Inside the composer, above the kept draft (A1).
  const hintBox = await refusal.boundingBox();
  const inputBox = await input.boundingBox();
  expect(hintBox && inputBox && hintBox.y + hintBox.height <= inputBox.y + 1).toBe(true);
  // The card is unchanged, still decidable, and the thread gained nothing.
  expect(await page.getByTestId("approval").innerText()).toBe(card);
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  await expect(page.getByTestId("thread-run")).toHaveCount(2);
  await expect(page.getByTestId("thread")).not.toContainText("also add 10 of hinge H-3");
  expect(api.messages).toHaveLength(1);
  expect(api.messageStarts).toBe(0);
  expect(api.decisions).toHaveLength(0);
});

test("the refusal hint clears once its run ends; the draft stays (B-1)", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  api.refuseMessages = HINT_BUSY;
  await api.install(page);
  await openThread(page);
  await expect(page.getByTestId("approval-approve")).toBeEnabled();
  const input = page.getByTestId("composer-input");
  await send(page, "approve it");
  const refusal = page.getByTestId("composer").getByTestId("refusal");
  await expect(refusal).toBeVisible();
  const hintId = await refusal.getByTestId("refusal-hint").getAttribute("id");
  expect(hintId).toBeTruthy();
  expect(await input.getAttribute("aria-describedby")).toContain(hintId);

  // The run ends (the approval was decided): the hint no longer describes the state.
  api.refuseMessages = null;
  api.finish(RUN_ID, "Draft order PO-SAMPLE-1 (sample).");
  await expect(page.getByTestId("thread-run").nth(1).getByTestId("run-card-status")).toHaveAttribute(
    "data-state",
    "SUCCEEDED",
  );
  await expect(refusal).toHaveCount(0);
  // The draft is kept and the composer is usable, no longer described by a hint.
  await expect(input).toHaveValue("approve it");
  await expect(input).toBeEnabled();
  expect((await input.getAttribute("aria-describedby")) ?? "").not.toContain(hintId);
  expect(api.messages).toHaveLength(1);
});

test("a run that needs review shows no verified line from an inner step (B-2)", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.waitingForApproval();
  // An earlier answer action inside the same run was verified (the recommendation step).
  api.emit("outcome.reported", { status: "VERIFIED", checks: [] });
  await api.install(page);
  await openThread(page);
  const card = page.getByTestId("thread-run").nth(1);
  await expect(card.getByTestId("run-card-status")).toHaveAttribute("data-state", "WAITING_APPROVAL");
  const line = card.getByTestId("run-card-line");
  // The line names what the badge says waits: the approval (PR-19).
  await expect(line).toContainText("Approval requested");
  await expect(line).not.toContainText("verified");
  // The earlier run ended verified, and says so.
  await expect(page.getByTestId("thread-run").nth(0).getByTestId("run-card-line")).toContainText(
    "Outcome verified",
  );

  // Once the run itself ends verified, its line may say so.
  api.finish(RUN_ID, "Draft order PO-SAMPLE-1 (sample).");
  await expect(card.getByTestId("run-card-status")).toHaveAttribute("data-state", "SUCCEEDED");
  await expect(line).toContainText("Outcome verified");
  expect(api.decisions).toHaveLength(0);
});

test("a new run is announced politely", async ({ page }) => {
  const api = onApi();
  api.twoRunThread();
  api.finish(RUN_ID, "Draft order PO-SAMPLE-1 (sample).");
  await api.install(page);
  await openThread(page);

  const announcer = page.getByTestId("thread-announcer");
  await expect(announcer).toHaveAttribute("role", "status");
  await expect(announcer).toHaveText("Run 2: Completed · verified");
  const input = page.getByTestId("composer-input");
  // Hold the send so the user can keep typing while it is in flight.
  let release = () => {};
  const held = new Promise<void>(resolve => (release = resolve));
  await page.route(/\/v1\/conversations\/[^/]+\/messages$/, async route => {
    await held;
    await route.fallback();
  });
  await input.click();
  await send(page, "and the next one");
  await input.pressSequentially(" then B-14");
  release();
  await expect(page.getByTestId("thread-run")).toHaveCount(3);
  await expect(announcer).toHaveText("Run 3: Working on it");
  // Announced without moving focus, and never as an alert (EA-16); only the sent text is cleared.
  await expect(input).toBeFocused();
  await expect(input).toHaveValue("then B-14");
  await expect(page.locator('[aria-live="assertive"], [role="alert"]')).toHaveCount(0);
  expect(api.messageStarts).toBe(1);
});

test("the thread stop slot stays in place: enabled while the latest run is active, disabled with a reason otherwise", async ({
  page,
}) => {
  const api = onApi();
  api.twoRunThread();
  api.state = "RUNNING";
  await api.install(page);
  await openThread(page);
  const slot = page.getByTestId("stop-slot");
  await expect(slot.getByTestId("stop")).toBeEnabled();
  await expect(page.getByTestId("thread-run").nth(1).getByTestId("run-card-stop")).toBeEnabled();

  api.finish(RUN_ID);
  await expect(slot.getByTestId("stop")).toBeDisabled();
  await expect(slot.getByTestId("stop-reason")).toHaveText("Nothing is running");
  await expect(slot.getByTestId("stop")).toHaveAttribute("aria-describedby", /.+/);
  await expect(page.getByTestId("run-card-stop")).toHaveCount(0);
});

test("the thread stop slot offers the safe check, not Stop, while the result is unconfirmed", async ({
  page,
}) => {
  const api = onApi();
  api.twoRunThread();
  api.state = "NEEDS_RECONCILIATION";
  await api.install(page);
  await openThread(page);
  const slot = page.getByTestId("stop-slot");
  await expect(slot.getByTestId("stop")).toBeDisabled();
  await expect(slot.getByTestId("stop-reason")).toHaveText(
    "Stopping is unavailable while the result is unconfirmed",
  );
  await expect(slot.getByTestId("stop-reconcile")).toHaveText("Check operation status");
});

for (const mode of ["off", "shadow"] as const) {
  test(`the ${mode} profile shows today's per-run view`, async ({ page }) => {
    const api = new MockApi().waitingForApproval();
    api.features = mode;
    await api.install(page);
    await page.goto("/?layout=sidebar");
    await send(page, "restock");
    await expect(page.getByTestId("approval-approve")).toBeEnabled();
    await expect(page.getByTestId("run-status")).toBeVisible();
    // Today's per-run view: no thread, no workspace, the locked composer, today's list.
    await expect(page.getByTestId("thread")).toHaveCount(0);
    await expect(page.getByTestId("artifact-workspace")).toHaveCount(0);
    await expect(page.getByTestId("stop-slot")).toHaveCount(0);
    await expect(page.getByTestId("thread-list")).toHaveCount(0);
    await expect(page.getByTestId("composer-input")).toBeDisabled();
    await expect(page.getByTestId("new-task")).toHaveText(/New task/);
    expect(api.messageStarts + api.createRuns).toBe(1);
    expect(api.createRuns).toBe(mode === "off" ? 1 : 0);
  });
}

/** Each state the thread can be in, reached as a user would, for the axe check. */
const AXE_STATES: {
  name: string;
  viewport?: { width: number; height: number };
  reach(page: Page): Promise<void>;
}[] = [
  {
    name: "empty thread",
    reach: async page => {
      await onApi().install(page);
      await page.goto("/?layout=sidebar");
      await expect(page.getByTestId("thread-empty")).toBeVisible();
    },
  },
  {
    name: "decision open in the workspace",
    reach: async page => {
      const api = onApi();
      api.twoRunThread();
      api.waitingForApproval();
      await api.install(page);
      await openThread(page);
      await expect(page.getByTestId("approval-approve")).toBeEnabled();
    },
  },
  {
    name: "workspace closed",
    reach: async page => {
      const api = onApi();
      api.twoRunThread();
      api.waitingForApproval();
      await api.install(page);
      await openThread(page);
      await page.getByTestId("workspace-close").click();
      await expect(page.getByTestId("artifact-workspace")).toHaveCount(0);
    },
  },
  ...(["light", "dark", "high-contrast"] as const).map(theme => ({
    name: `refused message (${theme})`,
    reach: async (page: Page) => {
      const api = onApi();
      api.twoRunThread();
      api.waitingForApproval();
      api.refuseMessages = HINT_BUSY;
      await api.install(page);
      await page.goto(`/?theme=${theme}`);
      const row = page.getByTestId("thread-row").first();
      await row.click();
      // Send once the thread is shown, as a user would (the composer sends nothing before).
      await expect(page.getByTestId("thread-run")).toHaveCount(2);
      await expect(page.getByTestId("approval-approve")).toBeEnabled();
      await send(page, "also add 10");
      await expect(page.getByTestId("refusal")).toBeVisible();
    },
  })),
  {
    name: "verified result in the workspace",
    reach: async page => {
      const api = onApi();
      api.twoRunThread();
      api.finish(RUN_ID, "Draft order PO-SAMPLE-1 (sample).");
      await api.install(page);
      await openThread(page);
      await expect(page.getByTestId("artifact-workspace")).toBeVisible();
    },
  },
  {
    name: "narrow workspace",
    viewport: { width: 390, height: 844 },
    reach: async page => {
      const api = onApi();
      api.twoRunThread();
      api.waitingForApproval();
      await api.install(page);
      await openThread(page, SURFACES[1] as Surface);
      await page.getByTestId("thread-run").nth(1).getByTestId("run-card-open").click();
      await expect(page.getByTestId("artifact-workspace")).toBeVisible();
    },
  },
  {
    name: "legacy last-seen group",
    reach: async page => {
      const api = new MockApi().waitingForApproval();
      await api.install(page);
      await page.goto("/");
      await send(page, "restock");
      await expect(page.getByTestId("approval-approve")).toBeEnabled();
      api.features = "on";
      await page.reload();
      await expect(page.getByTestId("legacy-group")).toBeVisible();
    },
  },
  {
    name: "off per-run view",
    reach: async page => {
      await new MockApi().waitingForApproval().install(page);
      await page.goto("/");
      await send(page, "restock");
      await expect(page.getByTestId("approval-approve")).toBeEnabled();
    },
  },
];

for (const state of AXE_STATES) {
  test(`axe: thread state "${state.name}" has no WCAG 2.2 AA violation`, async ({ page }) => {
    if (state.viewport) await page.setViewportSize(state.viewport);
    await state.reach(page);
    const result = await runAxe(page);
    // The count is printed so a run shows how many rules it checked (PR-31).
    console.log(`axe ${state.name}: ${result.rules} rules, ${result.violations.length} violations`);
    expect(result.rules, "axe ran no rule").toBeGreaterThan(0);
    expect(result.violations).toEqual([]);
  });
}
