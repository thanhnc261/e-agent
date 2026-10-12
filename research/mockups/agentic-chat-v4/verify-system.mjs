import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
const require = createRequire(new URL("../../../ui/package.json", import.meta.url));
const { chromium } = require("@playwright/test");
const directory = fileURLToPath(new URL("./screenshots/system/", import.meta.url));
await mkdir(directory, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [],
  external = [];
page.on("pageerror", e => errors.push(e.message));
page.on("request", r => {
  if (!r.url().startsWith("http://127.0.0.1:4181/")) external.push(r.url());
});
const shot = name => page.screenshot({ path: `${directory}${name}.png` });
async function bounds() {
  assert.ok(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    `page overflow ${JSON.stringify(page.viewportSize())}`,
  );
  const bad = await page
    .locator(".ds-entry")
    .evaluateAll(es => es.filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.dataset.component));
  assert.deepEqual(bad, [], "component overflow");
}
try {
  await page.goto("http://127.0.0.1:4181/agentic-chat-v4/components.html");
  await page.locator(".ds-icon-tile").first().waitFor();
  assert.equal(await page.locator(".ds-icon-tile").count(), 46);
  assert.ok((await page.locator("[data-component]").count()) >= 28);
  await bounds();
  await shot("01-foundations");
  await page.locator("#activity-switch").click();
  assert.equal(await page.locator("#activity-switch").getAttribute("aria-checked"), "true");
  await page.locator("#sample-form button").click();
  assert.equal(await page.locator("#sample-email").getAttribute("aria-invalid"), "true");
  assert.equal(await page.locator("#sample-email").evaluate(e => e === document.activeElement), true);
  await page.locator("#sample-email").fill("name@example.com");
  await page.locator("#sample-form button").click();
  assert.match(await page.locator("#form-result").innerText(), /Nothing sent/);
  await page.locator("#source-search").fill("missing");
  assert.match(await page.locator("#filtered-sources").innerText(), /No matching/);
  await page.locator("#source-search").fill("scope");
  assert.equal(await page.locator("#filtered-sources .source-item").count(), 1);
  await page.locator('[data-fill="What happens next?"]').click();
  assert.equal(await page.locator("#kit-prompt").inputValue(), "What happens next?");
  await page.locator("#kit-composer [data-action=add-context]").click();
  assert.equal(await page.locator("#kit-composer-context .context-chip").count(), 1);
  await page.locator("#kit-composer .send-button").click();
  assert.match(await page.locator("#composer-result").innerText(), /What happens next/);
  assert.equal(await page.locator("#kit-composer .send-button").isDisabled(), true);
  await page.locator("#next-page").click();
  assert.match(await page.locator("#work-rows").innerText(), /Outcome unknown/);
  await page.locator("#previous-page").click();
  assert.match(await page.locator("#page-count").innerText(), /1 of 2/);
  await page.locator("#tab-draft").focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.locator("#tab-source").getAttribute("aria-selected"), "true");
  assert.equal(await page.locator("#panel-source").isVisible(), true);
  await page.keyboard.press("Home");
  assert.equal(await page.locator("#tab-draft").getAttribute("aria-selected"), "true");
  await page.locator("[data-dialog=confirm]").click();
  assert.equal(await page.locator("#kit-dialog").evaluate(e => e.open), true);
  assert.equal(await page.locator("#dialog-back").evaluate(e => e === document.activeElement), true);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("[data-dialog=confirm]").evaluate(e => e === document.activeElement), true);
  await page.locator("#notify-demo").click();
  assert.equal(await page.locator("#notification-demo").isVisible(), true);
  for (const theme of ["light", "dark", "high-contrast"]) {
    await page.locator("#theme").selectOption(theme);
    const danger = page.locator(".ds-button-danger");
    await danger.evaluate(async e => {
      getComputedStyle(e).backgroundColor;
      await Promise.all(e.getAnimations().map(a => a.finished));
    });
    const originalFill = await danger.evaluate(e => getComputedStyle(e).backgroundColor);
    await danger.hover();
    await danger.evaluate(async e => {
      getComputedStyle(e).backgroundColor;
      await Promise.all(e.getAnimations().map(a => a.finished));
    });
    assert.equal(
      await danger.evaluate(e => getComputedStyle(e).backgroundColor),
      originalFill,
      "Destructive hover loses fill",
    );
    assert.equal(
      await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme),
      theme === "dark" ? "dark" : "light",
    );
    if (theme === "high-contrast") {
      assert.notEqual(
        await page
          .locator(".ds-status")
          .first()
          .evaluate(e => getComputedStyle(e).borderTopColor),
        "rgba(0, 0, 0, 0)",
      );
    }
    await page.locator("#controls").scrollIntoViewIfNeeded();
    await bounds();
    await shot(`02-controls-${theme}`);
    await page.locator("#conversation-kit").scrollIntoViewIfNeeded();
    await shot(`03-conversation-${theme}`);
  }
  for (const [width, height] of [
    [320, 720],
    [390, 844],
    [600, 960],
    [768, 1024],
    [820, 1180],
    [1024, 768],
    [1440, 900],
    [1920, 1080],
    [844, 390],
  ]) {
    await page.setViewportSize({ width, height });
    await page.locator("#theme").selectOption("light");
    await page.evaluate(() => scrollTo(0, 0));
    await bounds();
    await shot(`04-catalog-${width}x${height}`);
    for (const id of ["forms", "conversation-kit", "work", "overlays"]) {
      await page.locator("#" + id).scrollIntoViewIfNeeded();
      await bounds();
      if (width === 320 || width === 768) await shot(`05-${id}-${width}`);
    }
    await page.locator("[data-dialog=confirm]").click();
    const box = await page.locator("#kit-dialog").boundingBox();
    assert.ok(
      box.x >= 0 && box.x + box.width <= width + 1 && box.y + box.height <= height + 1,
      "dialog outside viewport",
    );
    assert.ok(
      await page.locator("#kit-dialog").evaluate(e => e.scrollWidth <= e.clientWidth),
      "dialog overflow",
    );
    if (width === 320 || height === 390) await shot(`06-dialog-${width}`);
    await page.keyboard.press("Escape");
  }
  // Full chat in the same themes and short/touch-oriented viewport sizes.
  for (const [width, height, theme] of [
    [1440, 1000, "dark"],
    [390, 844, "dark"],
    [1440, 1000, "high-contrast"],
    [320, 720, "high-contrast"],
    [844, 390, "light"],
    [390, 500, "light"],
    [1920, 1080, "light"],
  ]) {
    await page.setViewportSize({ width, height });
    await page.goto(`http://127.0.0.1:4181/agentic-chat-v4/?theme=${theme}`);
    await page.locator("[data-start=handoff]").click();
    assert.equal(
      await page.locator("#prompt").evaluate(e => e === document.activeElement),
      true,
      "Starter focus must land in composer",
    );
    if (width > 800) {
      await page.locator(".collapsed-toggle").click();
      assert.equal(await page.locator(".expanded-toggle").evaluate(e => e === document.activeElement), true);
      assert.equal(await page.locator(".expanded-toggle").getAttribute("aria-expanded"), "true");
      await page.locator(".expanded-toggle").click();
      assert.equal(await page.locator(".collapsed-toggle").evaluate(e => e === document.activeElement), true);
    }
    if (width <= 800) await page.locator(".artifact-link").click();
    await page.locator("#workspace-tab-document").focus();
    await page.keyboard.press("ArrowRight");
    assert.equal(await page.locator("#workspace-tab-sources").getAttribute("aria-selected"), "true");
    assert.equal(
      await page.locator("#workspace-body").getAttribute("aria-labelledby"),
      "workspace-tab-sources",
    );
    await page.keyboard.press("Home");
    assert.equal(await page.locator("#workspace-tab-document").getAttribute("aria-selected"), "true");
    await page.locator("[data-action=reject]").click();
    assert.equal(await page.locator("#workspace-body").getAttribute("tabindex"), "0");
    assert.equal(await page.locator("#workspace-body").evaluate(e => e === document.activeElement), true);
    await page.locator("[data-action=refresh]").click();
    assert.ok(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      `chat overflow ${width}/${theme}`,
    );
    const foot = await page.locator(".workspace-footer").boundingBox();
    assert.ok(foot.y + foot.height <= height + 1, `footer clipped ${width}/${height}`);
    await shot(`07-chat-${width}x${height}-${theme}`);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("http://127.0.0.1:4181/agentic-chat-v4/components.html");
  await page.locator(".ds-pending svg").waitFor();
  assert.equal(
    await page.locator(".ds-pending svg").evaluate(e => getComputedStyle(e).animationName),
    "none",
  );
  await page.emulateMedia({ forcedColors: "active" });
  await page.locator("#controls").scrollIntoViewIfNeeded();
  await shot("08-forced-colors");
  await bounds();
  await page.goto("http://127.0.0.1:4181/agentic-chat-v4/");
  await page.locator("[data-start=handoff]").click();
  await shot("09-chat-forced-colors");
  assert.equal(await page.locator(".composer").evaluate(e => getComputedStyle(e).borderTopStyle), "solid");
  const touch = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });
  const touchPage = await touch.newPage();
  await touchPage.goto("http://127.0.0.1:4181/agentic-chat-v4/components.html");
  await touchPage.locator("#kit-prompt").waitFor();
  assert.ok(await touchPage.evaluate(() => matchMedia("(pointer: coarse)").matches));
  assert.equal(await touchPage.locator("#kit-prompt").evaluate(e => getComputedStyle(e).fontSize), "16px");
  assert.ok((await touchPage.locator(".context-button").boundingBox()).height >= 44);
  await touch.close();
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  console.log(
    "PASS: responsive catalog 320–1920px, tablet/landscape, 3 themes, forms, shared composer, tabs keyboard, dialog focus, table pagination, reduced motion/forced colors and chat viewport checks; no page errors/external requests.",
  );
} finally {
  await browser.close();
}
