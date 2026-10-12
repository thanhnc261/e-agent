/**
 * UI conformance (UI architecture §6), against a scripted API. Each check runs
 * for every target UI; a UI that offers approval must pass all of them.
 */
import { expect, test, type Page } from "@playwright/test";
import { MockApi, presentation } from "../src/mock-api.ts";
import { TARGETS, type UiTarget } from "../src/targets.ts";

async function startRun(page: Page, target: UiTarget, api: MockApi, lang: "en" | "vi" = "en") {
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(String(e)));
  await api.install(page);
  await page.goto(target.url(lang));
  await target.open(page);
  await page.getByTestId("composer-input").fill("restock widget-a");
  await page.getByTestId("composer-submit").click();
  return errors;
}

const approval = (page: Page) => page.getByTestId("approval");

for (const target of TARGETS) {
  test.describe(`${target.name} UI`, () => {
    test("public text appears incrementally and reconnect does not duplicate it", async ({ page }) => {
      const api = new MockApi();
      api.emit("run.created", { task: "public streaming" });
      api.emit("run.state_changed", { from: "CREATED", to: "RUNNING" });
      await startRun(page, target, api);
      api.emitText("Public ", true);
      await expect(page.getByTestId("streaming-message")).toHaveText("Public ");
      api.emitText("answer");
      await expect(page.getByTestId("streaming-message")).toHaveText("Public answer");
      await page.waitForTimeout(500);
      await expect(page.getByTestId("streaming-message")).toHaveText("Public answer");
      api.emit("message.final", { text: "Public answer" });
      api.state = "SUCCEEDED";
      api.emit("run.state_changed", { from: "RUNNING", to: "SUCCEEDED" });
      await expect(page.getByTestId("streaming-message")).toHaveCount(0);
      await expect(page.getByTestId("final-message")).toContainText("Public answer");
      expect(api.createRuns).toBe(1);
    });

    test("clarification answers the same run without creating or approving another", async ({ page }) => {
      const api = new MockApi();
      api.emit("run.created", { task: "clarify" });
      api.emit("input.requested", { question: "Which customer?" });
      api.emit("run.state_changed", { from: "RUNNING", to: "WAITING_INPUT" });
      api.state = "WAITING_INPUT";
      await startRun(page, target, api);
      await expect(page.getByTestId("clarification-question")).toHaveText("Which customer?");
      await page.getByTestId("composer-input").fill("customer:acme");
      await page.getByTestId("composer-submit").click();
      await expect(page.getByTestId("clarification-question")).toHaveCount(0);
      expect(api.inputs).toEqual([{ input: "customer:acme", expected_revision: 1 }]);
      expect(api.createRuns).toBe(1);
      expect(api.decisions).toHaveLength(0);
    });

    test("a conversational reply is labelled as not verified and waits for the user's turn", async ({
      page,
    }) => {
      test.skip(
        target.name === "reference",
        "the minimal reference UI renders no status badge or message labels",
      );
      const api = new MockApi();
      api.emit("run.created", { task: "hi" });
      api.emit("input.requested", { question: "Hello! What would you like me to do?", kind: "reply" });
      api.emit("run.state_changed", { from: "RUNNING", to: "WAITING_INPUT" });
      api.state = "WAITING_INPUT";
      await startRun(page, target, api);
      await expect(page.getByTestId("clarification-question")).toContainText(
        "Hello! What would you like me to do?",
      );
      await expect(page.getByTestId("reply-label")).toHaveText("Reply · not a verified result");
      await expect(page.getByTestId("run-state")).toContainText("Your turn");
      await expect(page.getByTestId("final-message")).toHaveCount(0);
    });

    test("a clarification without kind keeps its label and status (old rows)", async ({ page }) => {
      test.skip(
        target.name === "reference",
        "the minimal reference UI renders no status badge or message labels",
      );
      const api = new MockApi();
      api.emit("run.created", { task: "clarify" });
      api.emit("input.requested", { question: "Which customer?" });
      api.emit("run.state_changed", { from: "RUNNING", to: "WAITING_INPUT" });
      api.state = "WAITING_INPUT";
      await startRun(page, target, api);
      await expect(page.getByTestId("reply-label")).toHaveCount(0);
      await expect(page.getByTestId("run-state")).toContainText("Your answer is needed");
    });

    test("1. shows every material field, marks changes, shows findings", async ({ page }) => {
      const api = new MockApi().waitingForApproval(
        presentation({
          findings: [
            { rule_id: "PR-001", rule_version: "1", status: "PASS", message: "satisfied", evidence_ids: [] },
            {
              rule_id: "PR-004",
              rule_version: "1",
              status: "UNKNOWN",
              message: "fact missing",
              evidence_ids: [],
            },
          ],
        }),
      );
      await startRun(page, target, api);
      await expect(page.getByTestId("material-field")).toHaveCount(3);
      await expect(page.locator('[data-testid="material-field"][data-path="quantity"]')).toHaveAttribute(
        "data-changed",
        "true",
      );
      await expect(page.locator('[data-testid="material-field"][data-path="unit_price"]')).toHaveAttribute(
        "data-changed",
        "false",
      );
      await expect(page.getByTestId("finding")).toHaveCount(2);
      await expect(page.locator('[data-testid="finding"][data-status="UNKNOWN"]')).toBeVisible();
    });

    test("2a. approve is disabled on a digest mismatch", async ({ page }) => {
      const good = presentation();
      const tampered = {
        ...good,
        canonical_proposal: { ...good.canonical_proposal, arguments: { quantity: "4000" } },
      };
      const api = new MockApi().waitingForApproval(tampered);
      await startRun(page, target, api);
      await expect(page.getByTestId("approval-digest-mismatch")).toBeVisible();
      await expect(page.getByTestId("approval-approve")).toBeDisabled();
      await expect(page.getByTestId("approval-confirm")).toHaveCount(0);
      expect(api.decisions).toHaveLength(0);
    });

    test("2b. approve is disabled after expiry", async ({ page }) => {
      const api = new MockApi().waitingForApproval(
        presentation({ expires_at: new Date(Date.now() - 1000).toISOString() }),
      );
      await startRun(page, target, api);
      await expect(page.getByTestId("approval-expired")).toBeVisible();
      await expect(page.getByTestId("approval-approve")).toHaveCount(0);
      await expect(page.getByTestId("approval-confirm")).toHaveCount(0);
    });

    test("2c. a new revision while confirming forces re-review", async ({ page }) => {
      const api = new MockApi().waitingForApproval();
      await startRun(page, target, api);
      await page.getByTestId("approval-approve").click();
      await expect(page.getByTestId("approval-confirm")).toBeVisible();
      // The server replaces the proposal (e.g. the agent repaired it).
      api.pending = presentation({ action_id: "act-2", run_revision: 9 }, "41");
      api.emit("approval.requested", { digest: api.pending.digest });
      await expect(page.getByTestId("approval-stale")).toBeVisible();
      await expect(page.getByTestId("approval-confirm")).toHaveCount(0);
      await page.getByTestId("approval-review-again").click();
      await expect(page.locator('[data-testid="material-field"][data-path="quantity"]')).toContainText("41");
      await expect(approval(page)).toHaveAttribute("data-phase", "reviewing");
      expect(api.decisions).toHaveLength(0);
    });

    test("3. dropped streams resume with no gaps, duplicates or repeated commands", async ({ page }) => {
      const api = new MockApi().waitingForApproval();
      api.chunk = 2;
      api.overlap = 2;
      await startRun(page, target, api);
      await expect(page.getByTestId("timeline-item")).toHaveCount(api.events.length);
      api.emit("validation.completed", { status: "PASS" });
      api.emit("read.recorded", { contract_id: "x" });
      api.emit("read.recorded", { contract_id: "y" });
      await expect(page.getByTestId("timeline-item")).toHaveCount(api.events.length);
      await page.waitForTimeout(600); // several more reconnects with overlapping replays
      await expect(page.getByTestId("timeline-item")).toHaveCount(api.events.length);
      expect(api.streamOpens).toBeGreaterThan(1);
      expect(api.createRuns).toBe(1);
      expect(api.decisions).toHaveLength(0);
    });

    test("4. model text never loads remote content and shows full link URLs", async ({ page }) => {
      const remote: string[] = [];
      page.on("request", r => {
        if (r.url().includes("evil.example")) remote.push(r.url());
      });
      const api = new MockApi();
      api.emit("run.created", {});
      api.emit("message.final", {
        text: "Done ![chart](https://evil.example/pixel.png) see [the docs](https://evil.example/phish?x=1) <img src=https://evil.example/i.png>",
      });
      api.emit("run.terminal", { state: "SUCCEEDED" });
      api.state = "SUCCEEDED";
      await startRun(page, target, api);
      const msg = page.getByTestId("final-message");
      await expect(msg).toContainText("https://evil.example/phish?x=1");
      await expect(msg).toContainText("<img src=https://evil.example/i.png>"); // shown as text
      await expect(page.getByTestId("blocked-image")).toHaveCount(1);
      await expect(msg.locator("img")).toHaveCount(0);
      await page.waitForTimeout(300);
      expect(remote).toEqual([]);
    });

    test("5. approval needs an explicit confirm; composer Enter never approves", async ({ page }) => {
      const api = new MockApi().waitingForApproval();
      await startRun(page, target, api);
      await expect(page.getByTestId("approval-approve")).toBeEnabled();
      await page.getByTestId("composer-input").evaluate(el => {
        el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      });
      await page.getByTestId("approval-approve").click();
      await page.getByTestId("approval-confirm-prompt").focus();
      await page.keyboard.press("Enter");
      await page.waitForTimeout(200);
      expect(api.decisions).toHaveLength(0);
      await page.getByTestId("approval-confirm").click();
      await expect.poll(() => api.decisions.length).toBe(1);
      expect(api.decisions[0]).toMatchObject({
        action_id: "act-1",
        expected_revision: 6,
        decision: "approved",
      });
      expect(api.decisions[0]?.["digest"]).toBe(api.pending?.digest);
    });

    test("6. an unknown event type refreshes the snapshot without crashing", async ({ page }) => {
      const api = new MockApi().waitingForApproval();
      const errors = await startRun(page, target, api);
      await expect(page.getByTestId("timeline-item")).toHaveCount(api.events.length);
      const before = api.snapshotReads;
      api.emit("brand.new.event", { anything: "<script>alert(1)</script>" });
      await expect(page.locator('[data-testid="timeline-item"][data-supported="false"]')).toHaveCount(1);
      await expect.poll(() => api.snapshotReads).toBeGreaterThan(before);
      await expect(page.getByTestId("material-field")).toHaveCount(3);
      expect(errors).toEqual([]);
    });

    test("7. Vietnamese labels render without overflow", async ({ page }) => {
      const long =
        "Đơn đặt hàng nháp cho nhà cung cấp được phê duyệt với số lượng và đơn giá đã kiểm tra ".repeat(4);
      const p = presentation();
      const api = new MockApi().waitingForApproval({
        ...p,
        material_fields: [
          ...p.material_fields,
          { path: "ghi_chu_rat_dai_khong_co_khoang_trang_".repeat(3), value: long, changed: false },
        ],
      });
      await startRun(page, target, api, "vi");
      await expect(approval(page)).toContainText("Xem xét thay đổi");
      await expect(page.getByTestId("approval-approve")).toContainText("phê duyệt");
      const overflow = await approval(page).evaluate(el => el.scrollWidth - el.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);
      const pageOverflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      );
      expect(pageOverflow).toBeLessThanOrEqual(0);
    });

    test("8. keyboard-only approval with visible focus", async ({ page }) => {
      const api = new MockApi().waitingForApproval();
      await startRun(page, target, api);
      await expect(page.getByTestId("approval-approve")).toBeEnabled();
      const activeTestId = () =>
        page.evaluate(() => {
          let a: Element | null = document.activeElement;
          while (a?.shadowRoot?.activeElement) a = a.shadowRoot.activeElement;
          return a?.getAttribute("data-testid") ?? null;
        });
      for (let i = 0; i < 60 && (await activeTestId()) !== "approval-approve"; i++)
        await page.keyboard.press("Tab");
      expect(await activeTestId()).toBe("approval-approve");
      const outline = await page
        .getByTestId("approval-approve")
        .evaluate(el => getComputedStyle(el).outlineStyle);
      expect(outline).not.toBe("none");
      await page.keyboard.press("Enter");
      await expect(page.getByTestId("approval-confirm")).toBeVisible();
      expect(await activeTestId()).not.toBe("approval-confirm"); // confirming needs its own action
      expect(api.decisions).toHaveLength(0);
      for (let i = 0; i < 10 && (await activeTestId()) !== "approval-confirm"; i++)
        await page.keyboard.press("Tab");
      expect(await activeTestId()).toBe("approval-confirm");
      await page.keyboard.press("Enter");
      await expect.poll(() => api.decisions.length).toBe(1);
    });
  });
}
