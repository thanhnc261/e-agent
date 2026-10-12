import { createRequire } from "node:module";
import assert from "node:assert/strict";
const require = createRequire(new URL("../../../ui/package.json", import.meta.url));
const { chromium, webkit } = require("@playwright/test");
for (const [name, engine] of Object.entries({ chromium, webkit })) {
  const browser = await engine.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("http://127.0.0.1:4181/agentic-chat-v4/identity.html");
    await page.locator("#identity-lockup svg").first().waitFor();
    for (const control of ["#identity-finish", "#identity-color-mode"])
      assert.ok((await page.locator(control).boundingBox()).height >= 44);
    for (const mode of ["brand", "multicolor"]) {
      await page.locator("#identity-color-mode").selectOption(mode);
      for (const finish of ["satin", "glossy"]) {
        await page.locator("#identity-finish").selectOption(finish);
        assert.equal(
          (await page.locator("#identity-lockup [data-finish] ellipse").count()) > 0,
          finish === "glossy",
        );
        for (const palette of ["soft-lagoon", "sage-lagoon", "sea-glass", "clay", "lavender", "blue"]) {
          await page.locator(`[data-palette="${palette}"]`).click();
          const colors = await page.locator("#identity-lockup .ea-brand-symbol").evaluate(svg => {
            const nodes = [...svg.querySelectorAll("[data-face] [data-node]")].map(
              node => getComputedStyle(node).fill,
            );
            return {
              nodes,
              brand: getComputedStyle(svg).color,
              edge: getComputedStyle(svg.querySelector("[data-face] path")).stroke,
            };
          });
          assert.equal(colors.nodes[2], colors.brand, "Center must retain brand");
          assert.equal(colors.edge, colors.brand, "Connections must retain brand");
          assert.equal(new Set(colors.nodes).size, mode === "brand" ? 1 : 5, "Node colors must be distinct");
          assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
          assert.ok(
            await page.locator("#identity-selected-download").evaluate(async link => {
              const doc = new DOMParser().parseFromString(
                await (await fetch(link.href)).text(),
                "image/svg+xml",
              );
              const inline = document.querySelector("#identity-lockup .ea-brand-symbol");
              return [...inline.children].every((child, i) =>
                child.isEqualNode(doc.documentElement.children[i]),
              );
            }),
            "Selected SVG export differs",
          );
        }
      }
    }
    await page.locator('[data-palette="soft-lagoon"]').click();
    await page.screenshot({
      path: new URL(`./screenshots/glossy-multicolor-${name}-${width}.png`, import.meta.url).pathname,
      fullPage: true,
    });
    if (name === "chromium" && width === 1440) {
      await page
        .locator(".brand-hero")
        .screenshot({ path: new URL("./screenshots/glossy-multicolor-logo.png", import.meta.url).pathname });
      await page.locator("#identity-color-mode").selectOption("brand");
      await page
        .locator(".brand-hero")
        .screenshot({ path: new URL("./screenshots/glossy-brand-logo.png", import.meta.url).pathname });
    }
  }
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(
    `PASS ${name}: both materials and color modes, six brands, center/edge brand preservation, distinct outer nodes, matching SVG, 320/768/1440px.`,
  );
}
