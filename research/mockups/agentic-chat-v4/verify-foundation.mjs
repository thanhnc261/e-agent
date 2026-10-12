import { createRequire } from "node:module";
import { mkdir, readFile } from "node:fs/promises";
import assert from "node:assert/strict";
const require = createRequire(new URL("../../../ui/package.json", import.meta.url));
const engines = require("@playwright/test");
const engineName = process.env.EAGENT_BROWSER || "chromium";
const engine = engines[engineName];
if (!["chromium", "webkit", "firefox"].includes(engineName)) throw Error("Unsupported browser");
const output = new URL(`./screenshots/foundation/${engineName}/`, import.meta.url).pathname;
await mkdir(output, { recursive: true });
const browser = await engine.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", e => errors.push(e.message));
const base = "http://127.0.0.1:4181/agentic-chat-v4/";
const shot = name => page.screenshot({ path: `${output}${name}.png` });
const overlay = page.locator("#overlay-preview");
const tokenThemes = JSON.parse(
  await readFile(new URL("./design-system/generated/tokens.json", import.meta.url), "utf8"),
);
const mobileBreakpoint = parseFloat(tokenThemes.light["layout.mobile-breakpoint"]);
const typeTokens = Object.entries(tokenThemes.light).filter(([key]) => key.startsWith("font.size."));
const paragraphStyle = element => {
  const s = getComputedStyle(element);
  return [
    s.fontFamily,
    s.fontSize,
    s.fontStyle,
    s.fontVariant,
    s.textIndent,
    s.textShadow,
    s.tabSize,
    s.letterSpacing,
    s.lineHeight,
    s.textTransform,
  ];
};
async function bounds() {
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "host overflow");
  assert.ok(
    await overlay.locator(".overlay-interior").evaluate(e => e.scrollWidth <= e.clientWidth + 1),
    "overlay overflow",
  );
  const foot = await overlay.locator(".overlay-footer").boundingBox();
  assert.ok(foot.y + foot.height <= page.viewportSize().height + 1, "footer clipped");
  if (await overlay.locator(".overlay-chat").isVisible()) {
    const send = await overlay.locator(".send-button").boundingBox();
    assert.ok(send.y + send.height <= foot.y + 1, "Footer obscures Send");
    const messages = await overlay.locator(".overlay-messages").boundingBox();
    assert.ok(messages.height >= 48, "Conversation scroll area collapsed");
  }
}
try {
  await page.goto(base + "identity.html");
  await page.locator("#identity-sizes svg").first().waitFor();
  await shot("01-identity-desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await shot("02-identity-phone");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(base + "overlay.html");
  await overlay.locator("#overlay-prompt").waitFor();
  await overlay.locator("#overlay-prompt").fill("Keep this draft while I change placement.");
  const before = await overlay.locator("#review").evaluate(e => {
    const s = getComputedStyle(e);
    return [
      s.backgroundColor,
      s.color,
      s.fontFamily,
      s.fontSize,
      s.borderRadius,
      s.textTransform,
      s.letterSpacing,
    ];
  });
  const paragraphBefore = await overlay.locator(".overlay-messages p").first().evaluate(paragraphStyle);
  await page.locator("#host-stress").check();
  const after = await overlay.locator("#review").evaluate(e => {
    const s = getComputedStyle(e);
    return [
      s.backgroundColor,
      s.color,
      s.fontFamily,
      s.fontSize,
      s.borderRadius,
      s.textTransform,
      s.letterSpacing,
    ];
  });
  assert.deepEqual(after, before, "host styles leaked into overlay");
  assert.deepEqual(
    await overlay.locator(".overlay-messages p").first().evaluate(paragraphStyle),
    paragraphBefore,
    "Host text inheritance leaked",
  );
  assert.equal(
    await page.locator("#host-button").evaluate(e => getComputedStyle(e).backgroundColor),
    "rgb(156, 22, 68)",
    "host fixture did not exercise conflict",
  );
  await bounds();
  await shot("03-host-isolation");
  await overlay.locator("#close").click();
  const launcher = overlay.locator("#overlay-launcher");
  assert.equal(
    await launcher.evaluate(e => getComputedStyle(e).backgroundColor),
    `rgb(${[1, 3, 5].map(i => parseInt(tokenThemes.light["color.accent"].slice(i, i + 2), 16)).join(", ")})`,
    "Host styles changed launcher",
  );
  assert.equal((await launcher.locator("svg").boundingBox()).width, 32);
  await shot("03-launcher-isolation");
  await launcher.click();
  await page.locator("#host-stress").uncheck();
  for (const theme of ["light", "dark", "high-contrast"]) {
    await page.locator("#panel-theme").selectOption(theme);
    assert.equal(
      await overlay.locator("#review").evaluate(e => e.getAnimations().length),
      0,
      "Theme change must not animate foreground/background out of sync",
    );
    const t = JSON.parse(
      await readFile(new URL("./design-system/generated/tokens.json", import.meta.url), "utf8"),
    )[theme];
    assert.equal(
      (await overlay.evaluate(e => getComputedStyle(e).getPropertyValue("--ea-color-canvas"))).trim(),
      t["color.canvas"],
      "host theme selector failed",
    );
    assert.equal(
      await overlay.locator(".overlay-frame").evaluate(e => getComputedStyle(e).colorScheme),
      theme === "dark" ? "dark" : "light",
    );
    for (const width of [320, 420, 640, 1040]) {
      await page.locator("#panel-width").selectOption(String(width));
      await bounds();
      assert.equal(
        await overlay.locator("#overlay-prompt").inputValue(),
        "Keep this draft while I change placement.",
      );
      assert.equal(
        await overlay.locator(".overlay-work").isVisible(),
        width > mobileBreakpoint,
        "container did not drive layout",
      );
      assert.equal(await overlay.locator("#view-toggle").isVisible(), width <= mobileBreakpoint);
      if (width === 420 || width === 1040) await shot(`04-${theme}-${width}`);
    }
  }
  for (const width of ["640", "1040"]) {
    await page.locator("#panel-width").selectOption(width);
    await overlay.locator("#open-work").click();
    assert.equal(
      await overlay.locator(".overlay-work h2").evaluate(e => e.getRootNode().activeElement === e),
      true,
      "Artifact focus must be visible at every container width",
    );
    await page.locator("#panel-width").selectOption("420");
    await overlay.locator("#view-toggle").click();
  }
  await page.locator("#panel-width").selectOption("420");
  await page.locator("#panel-theme").selectOption("light");
  await overlay.locator("#open-work").click();
  assert.equal(await overlay.locator(".overlay-work").isVisible(), true);
  assert.equal(await overlay.locator(".overlay-chat").isVisible(), false);
  await overlay.locator("#review").click();
  await overlay.locator("#confirm").click();
  assert.equal(await overlay.locator("#review-result").isVisible(), true);
  assert.match(await overlay.locator("#review-result").innerText(), /No business action/);
  await overlay.locator("#view-toggle").click();
  assert.equal(
    await overlay.locator("#overlay-prompt").inputValue(),
    "Keep this draft while I change placement.",
  );
  await overlay.locator("#review").click();
  assert.equal(await overlay.locator("#back").evaluate(e => e.getRootNode().activeElement === e), true);
  await page.keyboard.press("Escape");
  assert.equal(await overlay.locator("#review").evaluate(e => e.getRootNode().activeElement === e), true);
  await overlay.locator("#close").click();
  assert.equal(await page.locator("#overlay-launcher").isVisible(), true);
  assert.equal(
    await page.locator("#overlay-launcher").evaluate(e => e.getRootNode().activeElement === e),
    true,
  );
  await page.locator("#overlay-launcher").click();
  assert.equal(
    await overlay.locator("#overlay-prompt").inputValue(),
    "Keep this draft while I change placement.",
  );
  // Independent theme roots on the same host: no mutation of document or sibling tokens.
  await page.evaluate(() => {
    const other = document.createElement("e-agent-foundation-preview");
    other.id = "second-preview";
    other.dataset.theme = "dark";
    other.style.cssText = "position:relative;width:420px;height:600px";
    document.body.append(other);
  });
  const second = page.locator("#second-preview");
  await second.locator("#overlay-prompt").waitFor();
  assert.notEqual(
    await overlay.evaluate(e => getComputedStyle(e).getPropertyValue("--ea-color-canvas")),
    await second.evaluate(e => getComputedStyle(e).getPropertyValue("--ea-color-canvas")),
  );
  await page.evaluate(() => {
    const style = document.createElement("style");
    style.id = "hidden-conflict";
    style.textContent = "e-agent-foundation-preview[hidden]{display:block!important}";
    document.head.append(style);
  });
  await second.evaluate(e => (e.hidden = true));
  assert.equal(await second.isVisible(), false, "Portable hidden host rule missing");
  await page.locator("#hidden-conflict").evaluate(e => e.remove());
  await second.evaluate(e => e.remove());
  await page.evaluate(async () => {
    const { bindTabKeys } = await import("/agentic-chat-v4/design-system/components.js");
    const root = document.querySelector("#overlay-preview").shadowRoot;
    const tabs = document.createElement("div");
    tabs.innerHTML = '<button role="tab">First</button><button role="tab">Second</button>';
    root.append(tabs);
    bindTabKeys(tabs, button => (button.dataset.selected = "true"));
    tabs.firstElementChild.focus();
    tabs.firstElementChild.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    if (root.activeElement !== tabs.lastElementChild || tabs.lastElementChild.dataset.selected !== "true")
      throw Error("Shared tab keys failed inside Shadow DOM");
    tabs.remove();
  });
  for (const [width, height] of [
    [320, 720],
    [390, 844],
    [768, 1024],
    [844, 390],
  ]) {
    await page.setViewportSize({ width, height });
    await bounds();
    if (width <= mobileBreakpoint) {
      await overlay.locator(".overlay-frame[aria-modal=true]").waitFor();
      assert.equal(await page.locator(".host-controls").evaluate(e => e.inert), true);
      assert.equal(await overlay.locator(".overlay-frame").getAttribute("aria-modal"), "true");
      await overlay.locator("#review").focus();
      await page.keyboard.press("Tab");
      assert.equal(
        await overlay.evaluate(e => e.shadowRoot.activeElement?.id),
        "close",
        `Full-screen Tab cycle at ${width}px`,
      );
    }
    await shot(`05-viewport-${width}x${height}`);
    await overlay.locator("#review").click();
    const box = await overlay.locator("#review-dialog").boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= width + 1 && box.y >= 0 && box.y + box.height <= height + 1);
    await page.keyboard.press("Escape");
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.waitForFunction(() => !document.querySelector(".host-controls").inert);
  assert.equal(await page.locator(".host-controls").evaluate(e => e.inert), false);
  // Increase overlay text to 200% through the public font tokens; layout must retain its controls.
  await overlay.evaluate((e, tokens) => {
    for (const [name, value] of tokens)
      e.style.setProperty("--ea-" + name.replaceAll(".", "-"), `${parseFloat(value) * 2}px`);
  }, typeTokens);
  await bounds();
  await shot("06-enlarged-text");
  await overlay.evaluate((e, tokens) => {
    for (const [name] of tokens) e.style.removeProperty("--ea-" + name.replaceAll(".", "-"));
  }, typeTokens);
  // Long localized labels and unbroken source identifiers in a narrow docked container.
  await page.locator("#panel-width").selectOption("320");
  await overlay.locator("#open-work").click();
  await overlay
    .locator(".overlay-work h2")
    .evaluate(e => (e.textContent = "Bàn giao dự án — phạm vi và trách nhiệm cần xác nhận"));
  await overlay
    .locator(".overlay-work dd")
    .first()
    .evaluate(e => (e.textContent = "source_revision_" + "0123456789".repeat(15)));
  assert.ok(
    await overlay.locator(".overlay-work").evaluate(e => e.scrollWidth <= e.clientWidth + 1),
    "long content overflow",
  );
  await shot("07-long-content");
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await bounds();
  assert.equal(
    await overlay.locator(".overlay-interior").evaluate(e => getComputedStyle(e).borderTopStyle),
    "solid",
  );
  await shot("08-forced-colors");
  assert.deepEqual(errors, []);
  console.log(
    `PASS candidate harness (${engineName}): vector identity, Shadow DOM host isolation, host themes, independent instances, 320–1040px containers on desktop, retained drafts, safe modal focus, phone/tablet/landscape, enlarged text, long localized content and forced colors.`,
  );
} finally {
  await browser.close();
}
