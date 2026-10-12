import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
const require = createRequire(new URL("../../../ui/package.json", import.meta.url));
const { chromium } = require("@playwright/test");
const output = fileURLToPath(new URL("./screenshots/", import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 1,
});
const errors = [],
  external = [];
page.on("pageerror", e => errors.push(e.message));
page.on("request", r => {
  if (!r.url().startsWith("http://127.0.0.1:4181/")) external.push(r.url());
});
const act = name => page.locator(`[data-action="${name}"]`).filter({ visible: true }).first().click();
const shot = name => page.screenshot({ path: output + name + ".png" });
async function bounds() {
  if (await page.locator(".welcome").isVisible()) {
    const welcome = await page.locator(".welcome").boundingBox();
    const composer = await page.locator(".composer").boundingBox();
    assert.ok(welcome.y + welcome.height <= composer.y, "welcome overlaps composer");
  }
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "page overflow");
  for (const selector of [".composer", "#workspace", ".workspace-footer"])
    if (await page.locator(selector).isVisible()) {
      const b = await page.locator(selector).boundingBox();
      const v = page.viewportSize();
      assert.ok(b.x >= 0 && b.x + b.width <= v.width + 1, selector + " outside width");
      assert.ok(b.y + b.height <= v.height + 1, selector + " clipped below viewport");
    }
}
async function confirm() {
  await act("approve");
  assert.equal(await page.evaluate(() => document.activeElement.id), "dialog-title");
  await page.keyboard.press("Enter");
  assert.equal(await page.locator("[data-action=verify]").count(), 0);
  await act("confirm");
  await act("verify");
}
async function example(id) {
  await act("new");
  await page.locator("#prompt").fill("Explore a sample");
  await page.locator("#composer").evaluate(e => e.requestSubmit());
  await page.locator(`#dialog [data-start="${id}"]`).click();
}
try {
  await page.goto("http://127.0.0.1:4181/agentic-chat-v4/");
  await page.locator("[data-start=handoff]").waitFor();
  await bounds();
  assert.equal(await page.locator("#workspace").isVisible(), false);
  assert.ok((await page.locator("#sidebar").boundingBox()).width < 70);
  await shot("01-conversation");
  await page.locator("[data-start=handoff]").click();
  await bounds();
  await shot("02-chat-and-workspace");
  assert.ok(
    (await page.locator(".conversation").boundingBox()).width >
      (await page.locator("#workspace").boundingBox()).width,
    "chat must retain more width",
  );
  await page.locator("#prompt").fill("Keep this draft");
  const compact = await page.locator(".conversation").boundingBox();
  await page.locator(".collapsed-toggle").click();
  await bounds();
  assert.ok((await page.locator(".conversation").boundingBox()).width < compact.width);
  assert.equal(await page.locator("#prompt").inputValue(), "Keep this draft");
  await shot("03-navigation-expanded");
  assert.ok(
    (await page.locator(".conversation").boundingBox()).width >
      (await page.locator("#workspace").boundingBox()).width,
    "expanded navigation must not make workspace dominant",
  );
  await page.locator(".expanded-toggle").click();
  await act("close-workspace");
  assert.equal(await page.locator("#workspace").isVisible(), false);
  assert.equal(await page.locator("#prompt").inputValue(), "Keep this draft");
  await shot("04-conversation-focus");
  await act("workspace");
  assert.equal(await page.locator("#prompt").inputValue(), "Keep this draft");
  await page.locator("[data-tab=sources]").click();
  assert.equal(await page.locator(".source-item").count(), 3);
  await shot("05-sources");
  await page.locator("[data-tab=activity]").click();
  await page.locator(".simulation summary").click();
  await act("audience");
  await page.locator('[data-audience="Project owner only"]').click();
  await act("approve");
  assert.match(await page.locator("#dialog").innerText(), /Project owner only/);
  assert.match(await page.locator("#dialog").innerText(), /Acting identity/);
  assert.match(await page.locator("#dialog").innerText(), /Meridian launch/);
  await shot("06-exact-confirmation");
  await page.keyboard.press("Escape");
  await confirm();
  assert.match(await page.locator("#workspace").innerText(), /Alex Morgan · project owner only/);
  assert.doesNotMatch(await page.locator("#workspace").innerText(), /8 internal members/);
  await shot("07-separate-message");
  await page.locator("[data-tab=activity]").click();
  await page.locator(".simulation summary").click();
  await act("audience");
  assert.equal(
    await page.locator('[data-audience="Delivery team only"]').count(),
    0,
    "cannot widen document access through message audience",
  );
  await page.locator('[data-audience="Project owner only"]').click();
  await confirm();
  await act("evidence");
  assert.equal(await page.locator(".readback").count(), 2);
  assert.match(await page.locator("#dialog").innerText(), /Independent read-back/);
  await shot("08-readback");
  await page.keyboard.press("Escape");
  await page.locator("[data-tab=activity]").click();
  assert.equal(await page.locator("[data-scene]").count(), 0, "completed actions must not be rearmed");
  await page.locator("[data-tab=sources]").click();
  await act("new");
  await page.locator("[data-start=procurement]").click();
  await page.locator("#prompt").fill("Purchase draft note");
  await page.locator(".collapsed-toggle").click();
  await page.locator('[data-thread="1"]').click();
  assert.equal(await page.locator("#prompt").inputValue(), "Keep this draft");
  assert.equal(await page.locator("#workspace").isVisible(), true);
  assert.equal(await page.locator("[data-tab=sources]").getAttribute("aria-selected"), "true");
  await page.locator('[data-thread="2"]').click();
  assert.equal(await page.locator("#prompt").inputValue(), "Purchase draft note");
  await page.locator(".expanded-toggle").click();
  if (!(await page.locator("#workspace").isVisible())) await act("workspace");
  await page.locator("[data-tab=activity]").click();
  await page.locator(".simulation summary").click();
  await page.locator("[data-scene=unknown]").click();
  assert.equal(await page.locator("[data-action=approve]").count(), 0);
  assert.match(await page.locator("#workspace").innerText(), /Sent · unresolved/);
  await act("reconcile");
  await act("reconcile");
  assert.match(await page.locator("#dialog").innerText(), /No resend was attempted/);
  await page.keyboard.press("Escape");
  await shot("09-unknown");
  await page.locator("[data-tab=activity]").click();
  await page.locator(".simulation summary").click();
  assert.equal(
    await page.locator("[data-scene]").count(),
    0,
    "unknown cannot reset to review without explicit restart",
  );
  await act("restart");
  await page.locator("[data-tab=activity]").click();
  await page.locator(".simulation summary").click();
  await page.locator("[data-scene=stale]").click();
  assert.equal(await page.locator("[data-action=approve]").count(), 0);
  await act("refresh");
  assert.equal(await page.locator("[data-action=approve]").count(), 1);
  await example("knowledge");
  assert.equal(await page.locator("#workspace").isVisible(), false);
  await act("workspace");
  assert.equal(await page.locator("[data-action=approve]").count(), 0);
  assert.match(await page.locator("#messages").innerText(), /region/);
  await shot("10-read-only");
  await example("people");
  assert.match(await page.locator("#messages").innerText(), /No employee records/);
  assert.equal(await page.locator("#workspace").isVisible(), false);
  await example("service");
  await act("reject");
  assert.match(await page.locator("#messages").innerText(), /No action was sent/);
  await example("operations");
  await confirm();
  await act("evidence");
  assert.equal(await page.locator(".readback").count(), 1);
  await page.keyboard.press("Escape");
  await act("new");
  await page.locator("#prompt").fill("Cancelled sample prompt");
  await page.keyboard.press("Enter");
  await act("close-dialog");
  await page.locator(".starters [data-start=knowledge]").click();
  assert.doesNotMatch(await page.locator(".message.user").innerText(), /Cancelled sample prompt/);
  await act("new");
  await page.locator("#prompt").fill("<img src=x onerror=alert(1)>");
  await page.keyboard.press("Enter");
  await page.locator("#dialog [data-start=handoff]").click();
  assert.equal(await page.locator(".message.user img").count(), 0);
  assert.match(await page.locator(".message.user").innerText(), /<img/);
  await page.locator("#prompt").fill("Follow up");
  await page.keyboard.press("Enter");
  assert.equal(await page.locator(".message.user").count(), 2);
  assert.match(await page.locator("#messages").innerText(), /has not changed the proposal/);
  for (const width of [1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("http://127.0.0.1:4181/agentic-chat-v4/");
    await page.locator("[data-start=handoff]").waitFor();
    await bounds();
    await shot(`11-home-${width}`);
    await page.locator("[data-start=handoff]").click();
    if (width <= 800) {
      assert.equal(await page.locator("#workspace").isVisible(), false);
      await shot(`12-chat-${width}`);
      await act("workspace");
    }
    await bounds();
    await shot(`13-workspace-${width}`);
    await act("approve");
    await shot(`14-confirm-${width}`);
    await page.keyboard.press("Escape");
    await act("close-workspace");
    await page.locator("#prompt").fill("Retain on mobile");
    if (width <= 800) {
      await page.locator(".mobile-nav").click();
      assert.equal(await page.locator(".main").evaluate(e => e.inert), true);
      await shot(`15-drawer-${width}`);
      await page.keyboard.press("Escape");
      assert.equal(await page.locator(".main").evaluate(e => e.inert), false);
      assert.equal(await page.locator("#prompt").inputValue(), "Retain on mobile");
    }
    await bounds();
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("http://127.0.0.1:4181/agentic-chat-v4/");
  assert.equal(await page.locator(".send-button").isDisabled(), true);
  await page.locator("[data-start=handoff]").click();
  await page.locator(".source-trace summary").click();
  assert.equal(await page.locator(".source-trace .source-citation").count(), 3);
  await page.locator('[data-inspect-source="0"]').click();
  assert.match(await page.locator("#dialog").innerText(), /revision 4/);
  await page.keyboard.press("Escape");
  await act("add-context");
  await page.locator('[data-add-context="0"]').click();
  assert.match(await page.locator("#composer-context").innerText(), /Signed scope/);
  await page.locator(".collapsed-toggle").click();
  await page.locator(".expanded-toggle").click();
  assert.equal(await page.locator(".context-chip").count(), 1);
  await page.locator('[data-remove-context="0"]').click();
  assert.equal(await page.locator("#composer-context").isVisible(), false);
  await act("add-context");
  await page.locator('[data-add-context="0"]').click();
  const initialHeight = (await page.locator("#prompt").boundingBox()).height;
  await page.locator("#prompt").fill("Line one");
  await page.keyboard.press("Shift+Enter");
  assert.equal(await page.locator("#prompt").inputValue(), "Line one\n");
  await page.locator("#prompt").fill("Line one\nLine two\nLine three\nLine four\nLine five\nLine six");
  assert.ok((await page.locator("#prompt").boundingBox()).height > initialHeight);
  await page.locator('[data-suggest="What did you use to prepare this?"]').click();
  assert.equal(await page.locator(".message.user").count(), 1, "suggestion must not submit automatically");
  assert.equal(await page.locator(".send-button").isDisabled(), false);
  await bounds();
  await shot("16-composer-with-context");
  await page.locator(".send-button").click();
  assert.equal(await page.locator(".message.user").count(), 2);
  assert.match(await page.locator(".message.assistant").last().innerText(), /Signed scope.*revision 4/);
  assert.match(await page.locator(".sent-context").innerText(), /Signed scope/);
  assert.equal(await page.locator(".context-chip").count(), 0);
  assert.equal(await page.locator(".send-button").isDisabled(), true);
  assert.match(await page.locator("#workspace-footer").innerText(), /This action has not been sent/);
  await shot("17-follow-up");
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  console.log(
    "PASS: collapse/expand, workspace placement, retained drafts/thread state, six examples, exact separate approvals, clarified audience, read-back, stale/unknown, escaped input, 1440/1024/768/390/320 layouts; no page errors or external requests.",
  );
} finally {
  await browser.close();
}
