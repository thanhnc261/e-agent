import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
const require = createRequire(
  new URL("../../../ui/package.json", import.meta.url),
);
const { chromium } = require("@playwright/test");
const output = fileURLToPath(new URL("./screenshots/", import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1100 },
  deviceScaleFactor: 1,
});
const errors = [],
  external = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("request", (r) => {
  if (!r.url().startsWith("http://127.0.0.1:4180/")) external.push(r.url());
});
const shot = (name) =>
  page.screenshot({ path: `${output}${name}.png`, fullPage: false });
const action = (name) => page.locator(`#agent [data-action="${name}"]`).click();
const scene = (name) => page.locator("#scene").selectOption(name);
async function layout() {
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "horizontal page overflow",
  );
  if (await page.locator("#agent").isVisible()) {
    const box = await page.locator("#agent").boundingBox();
    const foot = await page.locator("#agent-footer").boundingBox();
    const studio = await page.locator(".studio").boundingBox();
    assert.ok(box.x >= 0, "clipped panel");
    assert.ok(
      foot.y + foot.height <= studio.y,
      "footer overlaps study controls",
    );
    assert.ok(
      await page
        .locator("#agent")
        .evaluate((e) => e.scrollWidth <= e.clientWidth),
      "horizontal panel overflow",
    );
  }
}
async function open(id) {
  if (await page.locator("#agent").isVisible())
    await page.locator("#minimize").click();
  await page.locator('[data-page="home"]').first().click();
  await page.locator(`.task-card[data-scenario="${id}"]`).click();
}
try {
  await page.goto("http://127.0.0.1:4180/");
  await page.locator(".task-card").first().waitFor();
  assert.equal(await page.locator(".task-card").count(), 6);
  await layout();
  await shot("01-workspace");
  await page.locator('[data-filter="People"]').click();
  assert.equal(await page.locator(".task-card").count(), 1);
  await page.locator('[data-filter="All"]').click();
  await page.locator('[data-page="connections"]').first().click();
  assert.equal(await page.locator(".connection-card").count(), 6);
  await shot("02-connections");
  await open("handoff");
  await layout();
  await shot("03-compact-review");
  await page.locator("#expand").click();
  await layout();
  await shot("04-expanded-review");
  await page.locator('.context-rail [data-source="0"]').click();
  assert.match(await page.locator("#modal").innerText(), /revision 4/);
  await shot("05-source-detail");
  await page.keyboard.press("Escape");
  await action("approve");
  assert.equal(
    await page.evaluate(() => document.activeElement.id),
    "modal-title",
  );
  await page.keyboard.press("Enter");
  assert.equal(await page.locator("#scene").inputValue(), "review");
  await shot("06-confirmation");
  await page.keyboard.press("Escape");
  await action("approve");
  await page.locator('#modal [data-action="confirm"]').click();
  assert.equal(await page.locator("#scene").inputValue(), "verifying");
  await action("advance");
  assert.equal(await page.locator("#scene").inputValue(), "review");
  assert.match(
    await page.locator("#agent-footer").innerText(),
    /Review 2 of 2/,
  );
  await shot("07-second-approval");
  await action("approve");
  await page.locator('#modal [data-action="confirm"]').click();
  await action("advance");
  assert.equal(await page.locator(".result-card").count(), 2);
  await shot("08-verified");
  await action("evidence");
  assert.equal(await page.locator(".verification-record").count(), 2);
  assert.match(
    await page.locator("#modal").innerText(),
    /Independent read-back service/,
  );
  assert.equal(await page.locator("#modal .source-card").count(), 0);
  await page.keyboard.press("Escape");
  await scene("unknown");
  await action("reconcile");
  assert.match(
    await page.locator("#agent-body").innerText(),
    /still unresolved/,
  );
  assert.equal(await page.locator('#agent [data-action="approve"]').count(), 0);
  await shot("09-unknown-outcome");
  assert.match(
    await page.locator(".mini-label").innerText(),
    /Sent · unresolved/,
  );
  await scene("stale");
  assert.equal(await page.locator('#agent [data-action="approve"]').count(), 0);
  await action("refresh");
  assert.match(await page.locator("#agent-footer").innerText(), /revision 2/);
  await scene("working");
  await shot("10-working");
  await scene("clarify");
  await page.locator("#audience").selectOption("Project owner only");
  await page.locator("#clarify-form button").click();
  assert.match(
    await page.locator(".scope-line").innerText(),
    /project owner only/i,
  );
  await page.locator("#minimize").click();
  await page.locator('[data-action="host"]').click();
  await page.locator('.host-card [data-scenario="handoff"]').click();
  await shot("11-in-context");
  await open("knowledge");
  assert.match(
    await page.locator("#agent-footer").innerText(),
    /No changes made/,
  );
  assert.equal(await page.locator('#agent [data-action="approve"]').count(), 0);
  assert.equal(await page.locator("#scene").isDisabled(), true);
  await shot("12-knowledge");
  await open("people");
  assert.match(
    await page.locator("#agent-body").innerText(),
    /No employee records/,
  );
  assert.equal(await page.locator("#scene").inputValue(), "blocked");
  await shot("13-missing-access");
  await open("service");
  assert.match(
    await page.locator(".artifact > .terms").innerText(),
    /Workplace IT/,
  );
  await action("reject");
  assert.match(
    await page.locator("#agent-body").innerText(),
    /No action was sent/,
  );
  await action("refresh");
  await shot("19-service-review");
  await open("procurement");
  await page.locator('[data-action="theme"]').click();
  assert.equal(
    await page.locator("body").evaluate((e) => getComputedStyle(e).color),
    "rgb(237, 238, 244)",
  );
  assert.equal(
    await page
      .locator("body")
      .evaluate((e) => getComputedStyle(e).backgroundColor),
    "rgb(23, 25, 31)",
  );
  await shot("14-dark-review");
  await page.locator('[data-action="theme"]').click();
  await page.locator("#minimize").click();
  await page.locator('[data-page="home"]').first().click();
  await page
    .locator("#intent")
    .fill("My sample request <img src=x onerror=alert(1)>");
  await page.locator("#intent-form button").click();
  await page.locator('#modal [data-scenario="operations"]').click();
  await page.locator(".request-summary summary").click();
  assert.match(
    await page.locator(".request-summary").innerText(),
    /My sample request/,
  );
  assert.equal(await page.locator(".request-summary img").count(), 0);
  await page.locator("#minimize").click();
  await page.locator("#launcher").click();
  await page.locator(".request-summary summary").click();
  assert.match(
    await page.locator(".request-summary").innerText(),
    /My sample request/,
  );
  await open("handoff");
  await scene("clarify");
  await page.locator("#audience").selectOption("Project owner only");
  await page.locator("#clarify-form button").click();
  await action("approve");
  assert.match(await page.locator("#modal").innerText(), /Project owner only/);
  await page.locator('#modal [data-action="confirm"]').click();
  await action("advance");
  assert.match(
    await page.locator(".artifact > .terms").innerText(),
    /Alex Morgan · project owner only/,
  );
  assert.doesNotMatch(
    await page.locator(".artifact > .terms").innerText(),
    /8 internal members/,
  );
  await action("approve");
  assert.match(
    await page.locator("#modal").innerText(),
    /Direct message \/ Alex Morgan/,
  );
  assert.doesNotMatch(
    await page.locator("#modal").innerText(),
    /8 internal members/,
  );
  await page.keyboard.press("Escape");
  await page.locator('#agent [data-action="approve"]').focus();
  await page.keyboard.press("n");
  assert.equal(await page.locator("#agent").isVisible(), true);
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await page.locator("#minimize").click();
    await page.locator('[data-page="home"]').first().click();
    await layout();
    const topbarGroups = await page
      .locator(".topbar > div")
      .evaluateAll((nodes) =>
        nodes.map((n) => {
          const r = n.getBoundingClientRect();
          return { left: r.left, right: r.right };
        }),
      );
    assert.ok(
      topbarGroups[0].right <= topbarGroups[1].left,
      "topbar group overlap",
    );
    await shot(`15-home-${width}`);
    await open("handoff");
    await layout();
    assert.ok(
      (await page
        .locator(".artifact-top .eyebrow")
        .evaluate((e) => parseFloat(getComputedStyle(e).fontSize))) >= 10,
    );
    const terms = await page.locator(".artifact > .terms").boundingBox();
    const preview = await page
      .locator(".document-preview")
      .first()
      .boundingBox();
    assert.ok(terms.y < preview.y, "terms must precede document content");
    await shot(`16-review-${width}`);
    await action("approve");
    await shot(`17-confirm-${width}`);
    await page.keyboard.press("Escape");
    await scene("unknown");
    await layout();
    await shot(`18-unknown-${width}`);
  }
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("http://127.0.0.1:4180/design-notes.html");
  assert.equal(await page.locator(".note-card").count(), 4);
  await shot("20-design-rationale");
  await page.goto("http://127.0.0.1:4180/design-system.html");
  assert.equal(await page.locator(".icon-tile").count(), 27);
  assert.equal(await page.locator(".mark svg").count(), 2);
  await page.screenshot({ path: `${output}23-identity.png`, fullPage: false });
  await page.screenshot({
    path: `${output}21-identity-components.png`,
    fullPage: true,
  });
  await page
    .locator("#components")
    .screenshot({ path: `${output}24-components.png` });
  await page.goto("http://127.0.0.1:4180/source-coverage.html");
  assert.equal(await page.locator("tbody tr").count(), 34);
  await page.goto("http://127.0.0.1:4180/design-system.html");
  await page.setViewportSize({ width: 390, height: 844 });
  await layout();
  await page.screenshot({
    path: `${output}22-identity-mobile.png`,
    fullPage: false,
  });
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  console.log(
    "PASS: six scenarios, filtering, connections, separate approvals, safe Enter, source inspection, stale and unknown states, clarification, draft/context retention, escaped text, dark theme, desktop/390/320 layouts; zero page errors or external requests.",
  );
} finally {
  await browser.close();
}
