// Mechanics check for study 05. Serve research/mockups on 127.0.0.1:4181 first (see README).
import { createRequire } from "node:module";
import { mkdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
const require = createRequire(new URL("../../../ui/package.json", import.meta.url));
const { chromium } = require("@playwright/test");
const output = fileURLToPath(new URL("./screenshots/", import.meta.url));
await mkdir(output, { recursive: true });
const BASE = "http://127.0.0.1:4181/agentic-chat-v5/";
const browser = await chromium.launch();
const results = [];
const ok = msg => results.push("ok   " + msg);

// Static check: no literal colours in v5 sources except the documented brand override.
for (const file of ["app.js", "identity-page.js", "identity.css"]) {
  const text = await readFile(new URL("./" + file, import.meta.url), "utf8");
  const hits = (text.match(/#[0-9a-f]{6}\b/gi) || []).filter(h => h.toLowerCase() !== "#4f8a74");
  assert.deepEqual(hits, [], `${file} has literal colours: ${hits}`);
}
const css = await readFile(new URL("./v5.css", import.meta.url), "utf8");
const cssColours = new Set((css.match(/#[0-9a-f]{6}\b/gi) || []).map(c => c.toLowerCase()));
cssColours.delete("#4f8a74"); // the documented brand override
cssColours.delete("#faf8f3"); // canvas value quoted in the override's comment
assert.deepEqual([...cssColours], [], "v5.css has undocumented literal colours");
ok("no literal colours outside the documented brand override");

async function newPage(viewport = { width: 1440, height: 1000 }, query = "") {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 });
  page.errors = [];
  page.external = [];
  page.on("pageerror", e => page.errors.push(e.message));
  page.on("console", m => m.type() === "error" && page.errors.push(m.text()));
  page.on("request", r => !r.url().startsWith("http://127.0.0.1:4181/") && page.external.push(r.url()));
  await page.goto(BASE + query);
  await page.locator("[data-start=handoff]").waitFor();
  return page;
}
const visible = (page, sel) => page.locator(sel).filter({ visible: true }).first();
const act = (page, name) => visible(page, `[data-action="${name}"]`).click();
async function studyDo(page, id) {
  if ((await page.locator("#study-toggle").getAttribute("aria-expanded")) !== "true")
    await page.locator("#study-toggle").click();
  await page.locator(`#study-panel [data-study="${id}"]`).click();
}
const status = page => page.locator("#run-status .ds-status").innerText();
async function bounds(page, name) {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: page overflow`);
  for (const sel of [".composer", "#workspace", ".workspace-footer", "#run-status"])
    if (await page.locator(sel).isVisible()) {
      const b = await page.locator(sel).boundingBox();
      const v = page.viewportSize();
      assert.ok(b.x >= -1 && b.x + b.width <= v.width + 1, `${name}: ${sel} outside width`);
    }
}
const shot = (page, name) => page.screenshot({ path: output + name + ".png" });
async function clean(page, name) {
  assert.deepEqual(page.errors, [], `${name}: page errors`);
  assert.deepEqual(page.external, [], `${name}: external requests`);
}

try {
  // 1. Entry: disclosure, identity, brand colour.
  let page = await newPage();
  assert.ok(await page.locator(".disclosure").isVisible(), "AI disclosure visible at entry");
  assert.match(await page.locator("#disclosure-title").innerText(), /AI agent/);
  assert.equal(
    await page.evaluate(() => getComputedStyle(document.querySelector(".welcome-mark")).color),
    "rgb(79, 138, 116)",
  );
  assert.equal(await page.locator(".welcome-mark svg [data-shadow]").count(), 0, "logo has no cast shadow");
  assert.ok((await page.locator('.welcome-mark svg [data-finish="glossy"] ellipse').count()) > 0, "glossy finish");
  ok("entry shows AI disclosure, v5 brand colour, shadowless glossy mark");
  await shot(page, "01-entry-light");

  // 2. Working → Stop → Stopped (nothing sent).
  await page.locator("[data-start=procurement]").click();
  assert.equal(await status(page), "Working");
  assert.ok(await page.locator("#run-status .stop-button").isVisible(), "Stop visible while working");
  assert.equal(await page.locator("#workspace").isVisible(), false);
  assert.match(await page.locator(".milestones").innerText(), /not finished/);
  assert.doesNotMatch(await page.locator("#messages").innerText(), /\d+%|seconds? left|ETA/i);
  await shot(page, "02-working");
  await page.locator("#run-status .stop-button").click();
  assert.equal(await status(page), "Stopped");
  assert.match(await page.locator("#messages").innerText(), /Nothing was proposed or sent/);
  assert.match(await page.locator("#announce").innerText(), /Stopped/);
  ok("working shows real milestones and Stop; stop reaches a stated safe state");
  await shot(page, "03-stopped");

  // 3. Restart → review with consequences, identity, AI origin; approval dialog focus.
  await studyDo(page, "restart");
  await studyDo(page, "finish-working");
  assert.equal(await status(page), "Needs review");
  assert.ok(await page.locator("#workspace .consequence").isVisible(), "consequence block visible");
  assert.match(await page.locator("#workspace .consequence").innerText(), /Reversible/);
  assert.match(await page.locator("#workspace .acting").innerText(), /Acts as/);
  assert.ok(await page.locator("#workspace .ai-origin").isVisible(), "AI-origin marker");
  assert.equal(await page.locator('#history button[aria-current="true"]').count(), 1);
  await shot(page, "04-review");
  await act(page, "approve");
  assert.equal(await page.evaluate(() => document.activeElement.id), "dialog-title", "dialog focuses heading, not approve");
  assert.ok(await page.locator("#dialog .consequence").isVisible());
  await page.keyboard.press("Enter");
  assert.ok(await page.locator("#dialog").isVisible(), "Enter on heading does not approve");
  await shot(page, "05-approve-dialog");
  await act(page, "confirm");

  // 4. Executing → commit → verifying → verified.
  assert.equal(await status(page), "Sending approved action");
  assert.match(await page.locator("#messages").innerText(), /not complete or verified yet/);
  assert.equal(await page.locator('#workspace .ds-status[data-tone="verified"]').count(), 0);
  await shot(page, "06-executing");
  await studyDo(page, "commit");
  assert.equal(await status(page), "Committed · checking result");
  await studyDo(page, "verify");
  assert.equal(await status(page), "Verified");
  ok("approve → executing → committed → verified are separate states");
  await shot(page, "07-verified");

  // 5. Failure and stop-in-flight paths.
  await studyDo(page, "restart");
  await studyDo(page, "finish-working");
  await act(page, "approve");
  await act(page, "confirm");
  await studyDo(page, "fail");
  assert.match(await status(page), /Failed/);
  assert.match(await page.locator("#messages").innerText(), /Nothing was created/);
  await shot(page, "08-failed");
  await act(page, "refresh");
  assert.equal(await status(page), "Needs review");
  await act(page, "approve");
  await act(page, "confirm");
  await page.locator("#run-status .stop-button").click();
  assert.equal(await status(page), "Outcome unknown");
  assert.match(await page.locator("#messages").innerText(), /will not resend/);
  assert.equal(await page.locator('[data-action="approve"]').count(), 0, "no resend path");
  ok("failure states cause and next step; stop in flight never resends");
  await shot(page, "09-stopped-in-flight");

  // 6. Stale proposal names what changed.
  await studyDo(page, "restart");
  await studyDo(page, "finish-working");
  await studyDo(page, "force-stale");
  assert.equal(await status(page), "Review outdated");
  assert.match(await page.locator("#messages").innerText(), /source changed after the draft was prepared \(/);
  ok("stale proposal names the changed source");

  // 6b. Needs input: the handoff asks who should receive it; answering prepares the proposal.
  await act(page, "new");
  await page.locator("[data-start=handoff]").click();
  await studyDo(page, "finish-working");
  assert.equal(await status(page), "Needs your input");
  assert.equal(await page.locator("#workspace").isVisible(), false);
  assert.ok(await page.locator("#run-status .stop-button").isVisible(), "Stop while waiting for input");
  await shot(page, "13-needs-input");
  await page.locator('#messages [data-audience="Project owner only"]').click();
  assert.equal(await status(page), "Needs review");
  assert.match(await page.locator("#workspace .scope").innerText(), /Project owner only/);
  await act(page, "audience");
  await page.locator('#dialog [data-audience="Delivery team only"]').click();
  assert.match(await page.locator("#workspace .overline").first().innerText(), /REVISION 2/);
  ok("needs input asks instead of guessing; changing the audience creates a new revision");

  // 7. Keyboard: close workspace returns focus; study harness is outside main.
  await visible(page, '[data-action="close-workspace"]').focus();
  await page.keyboard.press("Enter");
  assert.equal(await page.evaluate(() => document.activeElement.id), "reopen");
  assert.equal(await page.evaluate(() => document.querySelector("main").contains(document.querySelector(".study"))), false);
  ok("focus returns after closing the workspace; study controls sit outside the product surface");
  await clean(page, "flow");
  await page.close();

  // 8. Themes × widths.
  const sizes = [
    ["320", { width: 320, height: 720 }],
    ["390", { width: 390, height: 844 }],
    ["768", { width: 768, height: 1024 }],
    ["1440", { width: 1440, height: 900 }],
    ["landscape", { width: 844, height: 390 }],
  ];
  for (const theme of ["light", "dark", "high-contrast"])
    for (const [name, viewport] of sizes) {
      const p = await newPage(viewport, `?theme=${theme}`);
      assert.equal(await p.locator("#theme").inputValue(), theme);
      await bounds(p, `${theme}-${name}-entry`);
      await p.locator("[data-start=procurement]").click();
      await studyDo(p, "finish-working");
      if (await p.locator('[data-action="workspace"]').filter({ visible: true }).count())
        await act(p, "workspace");
      await bounds(p, `${theme}-${name}-review`);
      if (name === "390" || name === "1440") await shot(p, `10-${theme}-${name}`);
      await clean(p, `${theme}-${name}`);
      await p.close();
    }
  ok("3 themes × 5 viewports: no overflow, no errors, no external requests");

  // 9. Identity page.
  const id = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  id.errors = [];
  id.on("pageerror", e => id.errors.push(e.message));
  await id.goto(BASE + "identity.html");
  assert.match(await id.locator("#identity-pose-caption").innerText(), /15° clockwise · 35° backward tilt · subtle depth · no shadow · glossy/);
  assert.equal(await id.locator("#pose-v5 [data-shadow]").count(), 0);
  assert.ok((await id.locator("#pose-v4 [data-shadow]").count()) > 0, "v4 comparison keeps its shadow");
  assert.match(await id.locator("#identity-download").getAttribute("href"), /^blob:/);
  assert.equal(await id.locator("#identity-variants figure").count(), 4);
  for (const href of await id.locator("#identity-variants a").evaluateAll(as => as.map(a => a.href)))
    assert.match(href, /^blob:/);
  assert.ok(await id.locator("#launcher svg").isVisible(), "launcher specimen");
  assert.equal(await id.locator("#identity-sizes figure").count(), 6);
  await id.screenshot({ path: output + "11-identity.png", fullPage: true });
  await id.goto(BASE + "identity.html?theme=dark");
  await id.screenshot({ path: output + "12-identity-dark.png", fullPage: true });
  assert.deepEqual(id.errors, []);
  ok("identity page renders the v5 pose, comparison and download");
} finally {
  await browser.close();
}
console.log(results.join("\n"));
console.log(`\n${results.length} checks passed. Automated accessibility (axe) not run: no axe package is installed locally.`);
