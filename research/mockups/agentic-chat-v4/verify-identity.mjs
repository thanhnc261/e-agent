import { createRequire } from "node:module";
const require = createRequire(new URL("../../../ui/package.json", import.meta.url));
const { chromium, webkit } = require("@playwright/test");
const assert = require("node:assert/strict");
const output = new URL("./screenshots/", import.meta.url).pathname;
(async () => {
  for (const [name, engine] of Object.entries({ chromium, webkit })) {
    const browser = await engine.launch();
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    for (const width of [320, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto("http://127.0.0.1:4181/agentic-chat-v4/identity.html");
      await page.locator("#identity-lockup svg").first().waitFor();
      for (const control of ["#identity-depth", "#identity-tilt", "#identity-shadow"])
        assert.ok((await page.locator(control).boundingBox()).height >= 44, "Select touch target too small");
      for (const rotation of [15, 22.5, 30]) {
        await page.locator('[data-rotation="' + rotation + '"]').click();
        for (const tilt of ["20", "35", "45"])
          for (const depth of ["1", "3", "5"])
            for (const shadow of ["none", "soft", "raised"]) {
              await page.locator("#identity-shadow").selectOption(shadow);
              assert.equal(
                await page.locator("#identity-lockup [data-shadow]").count(),
                shadow === "none" ? 0 : 1,
              );
              await page.locator("#identity-depth").selectOption(depth);
              await page.locator("#identity-tilt").selectOption(tilt);
              assert.match(
                await page.locator("#identity-pose-caption").innerText(),
                new RegExp(rotation + "° clockwise"),
              );
              assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
              const box = await page.locator("#identity-lockup .ea-brand-symbol").evaluate(e => {
                const b = e.getBBox();
                return { x: b.x, y: b.y, w: b.width, h: b.height };
              });
              assert.ok(
                box.x >= 0 && box.y >= 0 && box.x + box.w <= 32 && box.y + box.h <= 32,
                "clipped projection",
              );
              assert.ok(
                await page.locator("#identity-selected-download").evaluate(async e => {
                  const svg = await (await fetch(e.href)).text();
                  const exported = new DOMParser().parseFromString(svg, "image/svg+xml").documentElement;
                  const inline = document.querySelector("#identity-lockup .ea-brand-symbol");
                  return (
                    exported.children.length === inline.children.length &&
                    [...inline.children].every((child, i) => child.isEqualNode(exported.children[i]))
                  );
                }),
                "download differs from selected geometry",
              );
            }
      }
      for (const palette of ["soft-lagoon", "sage-lagoon", "sea-glass", "clay", "lavender", "blue"]) {
        await page.locator('[data-palette="' + palette + '"]').click();
        assert.equal(
          await page.locator('[data-palette="' + palette + '"]').getAttribute("aria-pressed"),
          "true",
        );
        assert.ok(
          await page.locator("#identity-selected-download").evaluate(async e => {
            const svg = new DOMParser().parseFromString(
              await (await fetch(e.href)).text(),
              "image/svg+xml",
            ).documentElement;
            return (
              svg.getAttribute("color") ===
              getComputedStyle(document.documentElement).getPropertyValue("--ea-color-brand").trim()
            );
          }),
          "download differs from selected color",
        );
      }
      await page.locator('[data-palette="soft-lagoon"]').click();
      await page.locator("#identity-depth").selectOption("3");
      await page.locator("#identity-shadow").selectOption("soft");
      await page.locator('[data-rotation="22.5"]').click();
      await page.locator("#identity-tilt").selectOption("35");
      await page.screenshot({
        path: output + "shadow-identity-" + name + "-" + width + ".png",
        fullPage: true,
      });
      if (width === 1440 && name === "chromium")
        await page.locator(".brand-hero").screenshot({ path: output + "shadow-logo.png" });
      await page.goto("http://127.0.0.1:4181/agentic-chat-v4/palettes.html");
      await page.locator(".palette-card").nth(5).waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({
        path: output + "shadow-palettes-" + name + "-" + width + ".png",
        fullPage: true,
      });
    }
    assert.deepEqual(errors, []);
    await browser.close();
    console.log(
      "PASS " +
        name +
        ": 81 pose/shadow combinations at 320/768/1440px, no clipped geometry, matching selected SVG download, six palettes, no page errors.",
    );
  }
})();
