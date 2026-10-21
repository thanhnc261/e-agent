// Browser checks for the conversation thread mockup (Task 4e.2). Mechanics only, not design quality.
//   node research/mockups/conversation-thread-v1/verify.mjs          run every check, write screenshots
//   node research/mockups/conversation-thread-v1/verify.mjs --serve  only serve the mockup on 127.0.0.1:4183
// It serves an allow-list of files from the repository root (the mockup folder, the production token
// CSS and the owner logo), so nothing else in the checkout is reachable. Optional: AXE_CORE_PATH=<axe.min.js>.
import { createServer } from "node:http";
import { readFile, mkdir, rm } from "node:fs/promises";
import { existsSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { homedir } from "node:os";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../..");
const MOCK = "/research/mockups/conversation-thread-v1/";
const ALLOW = [MOCK, "/ui/packages/tokens/src/generated/tokens.css", "/ui/packages/components/src/primitives/brand/e-agent-mark.svg"];
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png" };

function serve(port) {
  const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    const p = decodeURIComponent(url.pathname);
    const ok = ALLOW.some(a => (a.endsWith("/") ? p.startsWith(a) : p === a)) && !p.includes("..");
    if (!ok) return res.writeHead(404).end("not served");
    const file = path.join(repo, p.endsWith("/") ? p + "index.html" : p);
    try {
      const body = await readFile(file);
      res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream", "cache-control": "no-store" }).end(body);
    } catch {
      res.writeHead(404).end("missing");
    }
  });
  return new Promise(resolve => server.listen(port, "127.0.0.1", () => resolve(server)));
}

if (process.argv.includes("--serve")) {
  await serve(4183);
  console.log(`Serving http://127.0.0.1:4183${MOCK} (Ctrl+C to stop)`);
} else {
  await run();
}

async function run() {
  const require = createRequire(path.join(repo, "ui/package.json"));
  const { chromium } = require("@playwright/test");
  const server = await serve(0);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const shots = path.join(here, "screenshots");
  await rm(shots, { recursive: true, force: true });
  await mkdir(shots, { recursive: true });

  // The brief's in-scope states (research 20, "Roles and states"), plus the reference sample for the
  // other normative states. A state missing from the mockup is a failure, not a skip.
  const REQUIRED = ["empty", "reply", "clarification", "running", "approval", "refused", "verified", "grounded", "failed", "ended-answer", "fallback", "legacy", "gallery"];
  const ACTIVE = new Set(["reply", "clarification", "running", "approval", "refused", "fallback"]);
  const VARIANTS = ["a1", "a2", "a3"];
  const WIDTHS = [[320, 720], [390, 844], [768, 1024], [1440, 1000], [844, 390]];
  const DENY = /\b(odoo|sap|netsuite|dynamics 365|oracle|quickbooks|xero|openai|anthropic|claude|gpt)\b/i;

  const axePath = process.env.AXE_CORE_PATH || [path.join(repo, "ui/node_modules/axe-core/axe.min.js")].find(existsSync);
  const axeSource = axePath && existsSync(axePath) ? await readFile(axePath, "utf8") : null;
  const axeVersion = axeSource ? (axeSource.match(/"(4\.\d+\.\d+)"/) || [])[1] || "unknown" : null;

  const results = [];
  const counts = {};
  async function check(group, name, fn) {
    counts[group] = (counts[group] || 0) + 1;
    try {
      await fn();
      results.push({ group, name, ok: true });
    } catch (e) {
      results.push({ group, name, ok: false, error: e.message.split("\n")[0] });
    }
  }
  const expect = (cond, msg) => {
    if (!cond) throw new Error(msg);
  };

  const browser = await chromium.launch();
  const external = [];
  const errors = [];
  async function newPage(viewport = { width: 1440, height: 1000 }, opts = {}) {
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, ...opts });
    const page = await ctx.newPage();
    page.on("request", r => { if (!r.url().startsWith(origin) && !r.url().startsWith("data:")) external.push(r.url()); });
    page.on("pageerror", e => errors.push(`pageerror: ${e.message}`));
    page.on("console", m => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
    return { ctx, page };
  }
  const url = (q = {}) => `${origin}${MOCK}index.html?${new URLSearchParams({ variant: "a1", state: "empty", lang: "en", theme: "light", surface: "page", ...q })}`;
  async function open(page, q) {
    await page.goto(url(q));
    await page.waitForSelector(`[data-state-sample="${q.state === "approved" ? "approved" : q.state || "empty"}"]`, { timeout: 5000 });
    await page.evaluate(() => document.fonts?.ready);
    await page.waitForFunction(() => [...document.images].every(i => i.complete));
  }
  const vis = (page, sel) => page.locator(sel).filter({ visible: true });
  async function noOverflow(page) {
    const r = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, w: innerWidth }));
    expect(r.sw <= r.w + 1, `horizontal overflow ${r.sw} > ${r.w}`);
  }
  async function axe(page, label) {
    if (!axeSource) return;
    await page.addScriptTag({ content: axeSource });
    const res = await page.evaluate(async () => {
      const r = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } });
      return r.violations.map(v => `${v.id}(${v.nodes.length}): ${v.nodes[0]?.target?.join(" ")}`);
    });
    expect(res.length === 0, `axe ${label}: ${res.join("; ")}`);
  }

  // Per-state content checks, in English. Each returns nothing or throws.
  const STATE_CHECKS = {
    empty: async (page) => {
      expect(/AI agent/.test(await page.locator("[data-testid=ai-disclosure]").innerText()), "AI disclosure missing (AG-DISC-1)");
      expect(await page.locator("[data-testid=capabilities] summary").count() === 1, "capability statement missing (AG-DISC-2)");
    },
    reply: async (page) => {
      expect(await page.getByText("Reply · not a verified result", { exact: true }).count() === 1, "first reply label must show once");
      expect(/Answering run 1/.test(await page.locator("[data-testid=answering]").innerText()), "answer not bound to run 1");
    },
    grounded: async (page, w) => {
      const s = await page.locator("[data-testid=run-status-1]");
      expect(/grounded, not verified/.test(await s.innerText()), "grounded label");
      expect((await s.getAttribute("data-tone")) !== "verified", "grounded must not use the verified tone (F-7)");
      expect(await vis(page, "[data-testid=agent-words-msg]").count() >= 1, "agent's words label on the message (G-B 5)");
      if (w >= 960) {
        expect(await vis(page, "[data-testid=workspace]").count() === 1, "workspace opens by itself for a result (G-B 6)");
        expect(await vis(page, "[data-testid=grounded-explain]").count() === 1, "grounded explanation line");
        expect(await vis(page, "[data-testid=agent-words-result]").count() === 1, "agent's words label on the result (G-B 5)");
        expect(await page.getByText("Value not recorded").count() >= 1, "citation value not recorded (EA-8)");
        expect(await page.getByText("A source that could not be matched").count() === 1, "unresolved citation");
      }
    },
    clarification: async (page) => {
      expect(/Answering run 2/.test(await page.locator("[data-testid=answering]").innerText()), "answer bound to run 2");
      expect(await page.getByText("A detail is needed to continue").count() === 1, "question label");
    },
    running: async (page) => {
      expect(await vis(page, "[data-testid=working-line]").count() === 1, "working line from a recorded event");
      expect(await vis(page, "[data-testid=stop-card]").count() === 1, "stop on the active run card");
      expect(!/%|seconds left|estimated/i.test(await page.locator("#app").innerText()), "no progress estimate (EA-5)");
    },
    approval: async (page, w) => {
      expect(/Needs review/.test(await page.locator("[data-testid=run-status-2]").innerText()), "needs review label");
      const focused = await page.evaluate(() => document.activeElement?.dataset?.key || document.activeElement?.tagName);
      expect(focused !== "approve" && focused !== "confirm", "approve must not hold initial focus (AG-APPR-8)");
      if (w >= 960) expect(await vis(page, "[data-testid=approval-card]").count() === 1, "workspace opens by itself with the card");
    },
    refused: async (page, w) => {
      expect(/conversation is busy/.test(await page.locator("[data-testid=refusal]").innerText()), "busy hint");
      expect((await page.locator("#prompt").inputValue()) === "also add 10 of hinge H-3", "draft kept");
      expect(await page.locator(".msg-user").filter({ hasText: "hinge H-3" }).count() === 0, "refused text must not appear as sent");
      if (w >= 960) expect(await vis(page, "[data-testid=approval-card]").count() === 1, "card still shown");
    },
    verified: async (page, w) => {
      const s = page.locator("[data-testid=run-status-2]");
      expect(/Completed · verified/.test(await s.innerText()) && (await s.getAttribute("data-tone")) === "verified", "verified label");
      expect(await vis(page, "[data-testid=agent-words-msg]").count() >= 1, "agent's words on the message");
      if (w >= 960) {
        expect(await vis(page, "[data-testid=verified-badge]").count() === 1, "verified result");
        expect(await vis(page, "[data-testid=agent-words-result]").count() === 1, "agent's words on the result");
      }
    },
    failed: async (page, w) => {
      expect(/Task stopped/.test(await page.locator("[data-testid=run-status-2]").innerText()), "failed label");
      if (w >= 960) expect(/Cause/.test(await page.locator("[data-testid=workspace]").innerText()), "cause shown");
    },
    "ended-answer": async (page) => {
      expect(/question changed/.test(await page.locator("[data-testid=refusal]").innerText()), "question-changed hint");
      expect((await page.locator("#prompt").inputValue()) === "40", "draft kept");
      expect(/Task cancelled/.test(await page.locator("[data-testid=run-status-2]").innerText()), "the thread shows how the run ended");
    },
    fallback: async (page) => {
      expect(await page.locator(".thread").count() === 0, "per-run view has no thread");
      expect(await vis(page, "[data-testid=mode-line]").count() === 1, "mode effect shown");
      expect(await page.locator("#prompt").isDisabled(), "today's locked composer while a decision waits");
      expect(/this task's messages/.test(await page.locator("[data-testid=context-used]").textContent()), "off/shadow keep the 4b.5 Context copy");
    },
    legacy: async (page) => {
      if (await vis(page, "[data-testid=legacy-group]").count() === 0) await vis(page, ".nav-toggle").click();
      const g = vis(page, "[data-testid=legacy-group]");
      expect(await g.count() === 1, "legacy group visible");
      expect(/last seen/.test(await g.innerText()), "legacy items marked last seen");
      expect(/Earlier tasks · this session · last seen/.test(await page.locator("#sidebar").innerText()), "legacy group heading");
      if (await vis(page, ".nav-close").count()) await vis(page, ".nav-close").click();
    },
    gallery: async (page) => {
      const cards = page.locator(".gallery-list > li");
      expect(await cards.count() === 7, "seven other normative states");
      expect(await page.locator("[data-testid=gallery-stop]").count() === 7, "every state shows its stop control");
      const recon = cards.filter({ hasText: "Result not confirmed" });
      expect(await recon.locator("[data-testid=gallery-stop]").isDisabled(), "no stop while unconfirmed (EA-4)");
      expect(await recon.getByText("Check operation status").count() === 1, "safe check, never a resend");
    },
  };

  try {
    // 0. Every required state exists in the mockup's registry.
    {
      const { ctx, page } = await newPage();
      await page.goto(url());
      await page.waitForSelector("[data-state-sample]");
      const states = await page.evaluate(() => window.__mock.states);
      for (const s of REQUIRED) await check("registry", `state ${s} present`, async () => expect(states.includes(s), `missing state: ${s}`));
      await ctx.close();
    }

    // 1. Every variant × state × width: renders, content, stop control, sample label, reflow, neutrality.
    for (const variant of VARIANTS) {
      for (const [width, height] of WIDTHS) {
        const { ctx, page } = await newPage({ width, height });
        for (const state of REQUIRED) {
          await check("states", `${variant} ${state} ${width}x${height}`, async () => {
            await open(page, { variant, state });
            await noOverflow(page);
            if (state === "legacy" && await vis(page, ".nav-close").count()) {
              // Narrow: the legacy sample opens on the drawer; the run view and its stop slot sit behind it.
              await vis(page, ".nav-close").click();
            }
            const slot = vis(page, "[data-testid=stop-slot]");
            expect(await slot.count() === 1, "stop slot missing (AG-CTRL-1)");
            const stopBtn = slot.locator("[data-testid=stop]");
            expect(await stopBtn.count() === 1, "stop control missing");
            const disabled = await stopBtn.isDisabled();
            if (ACTIVE.has(state)) expect(!disabled, "stop must be enabled on an active run");
            else expect(disabled && /Nothing is running/.test(await slot.innerText()), "stop disabled with a visible reason when nothing runs");
            expect(await vis(page, ".sample-badge").count() >= 1, "sample label (EA-11)");
            const bodyText = await page.locator("body").innerText();
            expect(!DENY.test(bodyText), "provider identifier in copy (PR-11)");
            expect(!/\b(null|undefined|NaN)\b|\b(status|approval|composer|outcome|citation|nav|run|empty|tab|ws|refused|gallery|carried|explain|fallback|legacy|messages|context|conversation|evidence|activity|proto|sample)\.[A-Za-z]/.test(bodyText), "a missing string or value leaked into the copy");
            await STATE_CHECKS[state](page, width);
            const cb = await vis(page, "#composer").boundingBox();
            expect(cb && cb.x >= 0 && cb.x + cb.width <= width + 1, "composer outside the width");
            // Screenshot set: every state at 1440 for each variant; every state at 390 for A1, and the
            // states where A2 and A3 look different at 390. Kept small because research files are permanent.
            const phoneSet = variant === "a1" || ["empty", "approval", "refused", "verified", "grounded", "ended-answer"].includes(state);
            if ((width === 1440 || (width === 390 && phoneSet)) && height !== 390) {
              await mkdir(path.join(shots, variant), { recursive: true });
              await page.screenshot({ path: path.join(shots, variant, `${state}-${width}.png`) });
            }
            if ((width === 320 || width === 768) && ["refused", "grounded", "verified", "empty"].includes(state)) await page.screenshot({ path: path.join(shots, variant, `${state}-${width}.png`) });
            if (height === 390 && ["refused", "verified"].includes(state)) await page.screenshot({ path: path.join(shots, variant, `${state}-landscape.png`) });
          });
          if ((width === 1440 || width === 390) && axeSource) await check("axe", `${variant} ${state} ${width}`, async () => axe(page, `${variant} ${state} ${width}`));
        }
        await ctx.close();
      }
    }

    // 2. Workspace: closes and reopens keeping the draft, focus returns to the opener (EA-10, AG-A11Y-2).
    for (const variant of VARIANTS) {
      await check("workspace", `${variant} desktop close/reopen keeps draft, focus returns`, async () => {
        const { ctx, page } = await newPage();
        await open(page, { variant, state: "approval" });
        expect(await vis(page, "[data-testid=workspace]").count() === 1, "auto-open on desktop");
        const card = await page.locator("[data-testid=approval-card]").innerText();
        await page.locator("#prompt").fill("keep this draft");
        await page.locator("[data-testid=ws-close]").click();
        expect(await vis(page, "[data-testid=workspace]").count() === 0, "workspace closed");
        expect((await page.evaluate(() => document.activeElement.dataset.key)) === "open-2", "focus returns to the run card's Open");
        expect((await page.locator("#prompt").inputValue()) === "keep this draft", "draft kept on close");
        expect(/Needs review/.test(await page.locator("[data-testid=run-card-2]").innerText()), "pending decision still visible on its run card");
        await page.keyboard.press("Enter");
        expect((await page.evaluate(() => document.activeElement.dataset.key)) === "ws-heading", "focus moves to the workspace heading on open");
        expect((await page.locator("[data-testid=approval-card]").innerText()) === card, "card unchanged after close/reopen");
        await page.keyboard.press("Escape");
        expect(await vis(page, "[data-testid=workspace]").count() === 0, "Escape closes");
        expect((await page.evaluate(() => document.activeElement.dataset.key)) === "open-2", "focus back on Escape");
        await ctx.close();
      });
      await check("workspace", `${variant} phone: no auto-open, view switch, Back returns focus`, async () => {
        const { ctx, page } = await newPage({ width: 390, height: 844 });
        await open(page, { variant, state: "approval" });
        expect(await vis(page, "[data-testid=workspace]").count() === 0, "no auto-open on a phone");
        await page.locator("#prompt").fill("phone draft");
        await page.locator("[data-testid=open-run-2]").click();
        await page.waitForFunction(() => [...document.images].every(i => i.complete));
        expect(await vis(page, "[data-testid=workspace]").count() === 1 && await vis(page, ".thread").count() === 0, "workspace replaces the conversation");
        await screenshot(page, variant, "approval-workspace-390");
        await vis(page, ".ws-back").click();
        expect((await page.evaluate(() => document.activeElement.dataset.key)) === "open-2", "Back returns focus");
        expect((await page.locator("#prompt").inputValue()) === "phone draft", "draft kept");
        await ctx.close();
      });
      await check("workspace", `${variant} tabs: arrow keys move selection`, async () => {
        const { ctx, page } = await newPage();
        await open(page, { variant, state: "verified" });
        await page.locator("#tab-result").focus();
        await page.keyboard.press("ArrowRight");
        expect((await page.evaluate(() => document.activeElement.id)) === "tab-decision", "ArrowRight to the next tab");
        expect((await page.locator("#tab-decision").getAttribute("aria-selected")) === "true", "selected");
        await page.keyboard.press("End");
        await screenshot(page, variant, "verified-activity-1440");
        await ctx.close();
      });
    }

    // 3. A refused message keeps the draft and leaves the card unchanged (ADR 0034 §2, G-B 4).
    for (const variant of VARIANTS) {
      await check("refusal", `${variant} send during approval is refused, draft kept, card unchanged`, async () => {
        const { ctx, page } = await newPage();
        await open(page, { variant, state: "approval" });
        const card = await page.locator("[data-testid=approval-card]").innerText();
        const sent = await page.locator(".msg-user").count();
        await page.locator("#prompt").fill("approve it");
        await page.keyboard.press("Enter");
        expect(/conversation is busy/.test(await page.locator("[data-testid=refusal]").innerText()), "server hint shown");
        expect((await page.locator("#prompt").inputValue()) === "approve it", "draft kept");
        expect((await page.locator("[data-testid=approval-card]").innerText()) === card, "card unchanged");
        expect((await page.locator(".msg-user").count()) === sent, "nothing added to the thread");
        expect(/Needs review/.test(await page.locator("[data-testid=run-status-2]").innerText()), "a message is never a decision");
        await ctx.close();
      });
    }

    // 4. Keyboard-only main path: hi → reply → question → grounded → PO → answer → running →
    //    approval → confirm (focus never on approve) → verifying → verified. Focus stays in the composer.
    for (const variant of VARIANTS) {
      await check("keyboard", `${variant} main path by keyboard`, async () => {
        const { ctx, page } = await newPage();
        await open(page, { variant, state: "empty" });
        await page.locator("#prompt").focus();
        const step = async (text, next) => {
          await page.keyboard.type(text);
          await page.keyboard.press("Enter");
          await page.waitForSelector(`[data-state-sample="${next}"]`);
          expect((await page.evaluate(() => document.activeElement.id)) === "prompt", `focus stayed in the composer after ${next} (EA-16)`);
        };
        await step("hi", "reply");
        await page.waitForFunction(() => /Your turn/.test(document.getElementById("announcer").textContent));
        await step("which products are short?", "grounded");
        await step("draft a PO for it", "clarification");
        await step("40", "running");
        await page.locator("#proto-next").click();
        await page.waitForSelector('[data-state-sample="approval"]');
        await page.locator("[data-testid=approve]").focus();
        await page.keyboard.press("Enter");
        expect((await page.evaluate(() => document.activeElement.dataset.key)) === "confirm-prompt", "confirm step focuses its prompt, not Confirm (AG-APPR-8)");
        await page.keyboard.press("Escape");
        expect((await page.evaluate(() => document.activeElement.dataset.key)) === "approve", "Escape backs out of confirm");
        await page.keyboard.press("Enter");
        await page.keyboard.press("Tab");
        expect((await page.evaluate(() => document.activeElement.dataset.key)) === "confirm", "Tab reaches Confirm");
        await page.keyboard.press("Enter");
        await page.waitForSelector('[data-state-sample="approved"]');
        expect(/Checking the outcome/.test(await page.locator("[data-testid=run-status-2]").innerText()), "approved is not verified (EA-3)");
        expect(!(await vis(page, "[data-testid=stop-slot] [data-testid=stop]").isDisabled()), "stop available while verifying");
        await page.locator("#proto-next").click();
        await page.waitForSelector('[data-state-sample="verified"]');
        await ctx.close();
      });
    }

    // 5. Stop reaches a safe state and says what happened (AG-CTRL-1).
    for (const variant of VARIANTS) {
      await check("stop", `${variant} stop while running`, async () => {
        const { ctx, page } = await newPage();
        await open(page, { variant, state: "running" });
        await vis(page, "[data-testid=stop-slot] [data-testid=stop]").click();
        await page.waitForSelector('[data-state-sample="stopped"]');
        expect(/Task cancelled/.test(await page.locator("[data-testid=run-status-2]").innerText()), "cancelled label");
        expect(/Stopped before any change was sent/.test(await page.locator("#app").innerText()), "in-flight status stated");
        expect(await vis(page, "[data-testid=stop-slot] [data-testid=stop]").isDisabled(), "nothing left to stop");
        await screenshot(page, variant, "stopped-1440");
        await ctx.close();
      });
    }

    // 6. Sidebar drawer on a phone (legacy sample): Escape closes and returns focus.
    for (const variant of VARIANTS) {
      await check("sidebar", `${variant} legacy drawer on a phone`, async () => {
        const { ctx, page } = await newPage({ width: 390, height: 844 });
        await open(page, { variant, state: "legacy" });
        await page.locator("[data-key=nav-first]").focus();
        await page.keyboard.press("Escape");
        expect((await page.evaluate(() => document.activeElement.dataset.key)) === "nav-toggle", "focus returns to the toggle");
        expect(await vis(page, "[data-testid=legacy-main]").count() === 1, "legacy run shown");
        await screenshot(page, variant, "legacy-main-390");
        await ctx.close();
      });
    }

    // 7. Themes, forced colours, reduced motion, 200 % text, Vietnamese, docked surface, fallback modes.
    for (const variant of VARIANTS) {
      for (const theme of ["dark", "high-contrast"]) {
        await check("themes", `${variant} ${theme}`, async () => {
          const { ctx, page } = await newPage();
          await open(page, { variant, state: "refused", theme });
          await noOverflow(page);
          await screenshot(page, variant, `refused-${theme}-1440`);
          await axe(page, `${variant} refused ${theme}`);
          await open(page, { variant, state: "grounded", theme });
          await axe(page, `${variant} grounded ${theme}`);
          await ctx.close();
        });
      }
      await check("themes", `${variant} forced colours`, async () => {
        const { ctx, page } = await newPage({ width: 1440, height: 1000 }, { forcedColors: "active" });
        await open(page, { variant, state: "refused" });
        expect(await vis(page, "[data-testid=approve]").count() === 1 && await vis(page, "[data-testid=stop]").count() === 1, "controls visible");
        await screenshot(page, variant, "refused-forced-colors-1440");
        await ctx.close();
      });
      await check("motion", `${variant} reduced motion removes transitions`, async () => {
        const { ctx, page } = await newPage({ width: 1440, height: 1000 }, { reducedMotion: "reduce" });
        await open(page, { variant, state: "approval" });
        const d = await page.locator("[data-testid=approve]").evaluate(e => getComputedStyle(e).transitionDuration);
        expect(/^0s(, 0s)*$/.test(d), `transition ${d}`);
        await ctx.close();
      });
      await check("text-200", `${variant} 200 % text`, async () => {
        const { ctx, page } = await newPage({ width: 1280, height: 900 });
        for (const state of ["refused", "verified", "grounded", "empty"]) {
          await open(page, { variant, state });
          await page.addStyleTag({ content: "html{font-size:200% !important}" });
          await noOverflow(page);
          if (state === "refused") await screenshot(page, variant, "refused-text200-1280");
        }
        await ctx.close();
      });
      await check("vi", `${variant} Vietnamese`, async () => {
        for (const [w, hgt] of [[320, 720], [390, 844], [1440, 1000]]) {
          const { ctx, page } = await newPage({ width: w, height: hgt });
          for (const state of REQUIRED) {
            await open(page, { variant, state, lang: "vi" });
            await noOverflow(page);
            expect((await page.evaluate(() => document.documentElement.lang)) === "vi", "lang attribute");
            const viSet = variant === "a1" ? ["refused", "grounded", "ended-answer", "legacy", "empty"] : ["refused"];
            if (viSet.includes(state) && w !== 320) await screenshot(page, variant, `vi-${state}-${w}`);
          }
          await open(page, { variant, state: "refused", lang: "vi" });
          expect(/Cuộc trò chuyện đang bận/.test(await page.locator("[data-testid=refusal]").innerText()), "VI busy hint (brief draft)");
          await open(page, { variant, state: "grounded", lang: "vi" });
          if (w >= 960) expect(/Có dẫn chứng: nguồn là các bản ghi/.test(await page.locator("[data-testid=grounded-explain]").innerText()), "VI grounded line");
          await ctx.close();
        }
      });
      await check("docked", `${variant} docked surface`, async () => {
        const { ctx, page } = await newPage();
        for (const state of ["refused", "running", "grounded"]) {
          await open(page, { variant, state, surface: "docked" });
          const w = await page.locator("#app").evaluate(e => e.clientWidth);
          expect(w <= 420, `docked width ${w}`);
          expect(await vis(page, "[data-testid=workspace]").count() === 0, "no auto-open in a narrow dock");
          await noOverflow(page);
          await screenshot(page, variant, `docked-${state}-1440`);
        }
        await ctx.close();
      });
    }
    for (const mode of ["off", "shadow", "features", "route-error"]) {
      await check("fallback", `mode ${mode}`, async () => {
        const { ctx, page } = await newPage({ width: 1440, height: 1000 });
        await open(page, { state: "fallback", mode });
        expect(await page.locator(".thread").count() === 0 && await page.locator("[data-testid=workspace]").count() === 0, "today's per-run view");
        if (mode === "features") expect(await vis(page, "[data-testid=fallback-notice]").count() === 1, "features failure stated");
        if (mode === "route-error") {
          expect(/not sent again/.test(await page.locator("[data-testid=route-error]").innerText()), "route error, no re-post");
          expect((await page.locator("#prompt").inputValue()) === "Supplier North", "draft kept");
        }
        await screenshot(page, "fallback", `${mode}-1440`);
        await page.setViewportSize({ width: 390, height: 844 });
        await noOverflow(page);
        await screenshot(page, "fallback", `${mode}-390`);
        await ctx.close();
      });
    }

    // 8. Hostile text stays inert (AG-ID-2): the sample renderer never parses HTML.
    await check("inert", "typed markup is not parsed", async () => {
      const { ctx, page } = await newPage();
      await open(page, { state: "approval" });
      await page.locator("#prompt").fill('<img src=x onerror="window.__pwned=1">');
      await page.keyboard.press("Enter");
      expect(await page.locator("#app img[src=x]").count() === 0 && !(await page.evaluate(() => window.__pwned)), "markup parsed");
      await ctx.close();
    });

    // 9. The overview image for the owner: three variants at the same moment.
    await check("overview", "compare.html", async () => {
      const { ctx, page } = await newPage({ width: 1440, height: 1200 });
      await page.goto(`${origin}${MOCK}compare.html`);
      for (const f of page.frames().slice(1)) await f.waitForSelector('[data-state-sample="refused"]');
      await page.waitForTimeout(150);
      await page.screenshot({ path: path.join(shots, "00-overview.png"), fullPage: true });
      await ctx.close();
    });

    await check("network", "no external requests", async () => expect(external.length === 0, external.slice(0, 3).join(", ")));
    await check("console", "no page or console errors", async () => expect(errors.length === 0, errors.slice(0, 3).join(" | ")));
  } finally {
    await browser.close();
    server.close();
  }

  async function screenshot(page, folder, name) {
    await mkdir(path.join(shots, folder), { recursive: true });
    await page.screenshot({ path: path.join(shots, folder, `${name}.png`) });
  }

  const failed = results.filter(r => !r.ok);
  const total = results.length;
  console.log(`conversation-thread-v1 verify · ${new Date().toLocaleDateString("sv-SE")}`);
  console.log(`states required: ${REQUIRED.length} (${REQUIRED.join(", ")}); variants: ${VARIANTS.join(", ")}; widths: ${WIDTHS.map(([w, h]) => `${w}x${h}`).join(", ")}`);
  console.log(axeSource ? `axe-core ${axeVersion} from ${path.relative(repo, axePath).startsWith("..") ? axePath.replace(homedir(), "~") : path.relative(repo, axePath)}` : "axe-core: NOT RUN (no axe.min.js; set AXE_CORE_PATH). Recorded as a gap.");
  for (const [g, n] of Object.entries(counts)) {
    const f = results.filter(r => r.group === g && !r.ok).length;
    console.log(`  ${g.padEnd(10)} ${String(n - f).padStart(4)}/${n} passed`);
  }
  for (const f of failed) console.log(`FAIL [${f.group}] ${f.name}: ${f.error}`);
  if (total === 0) {
    console.log("FAIL: zero cases ran");
    process.exit(1);
  }
  console.log(failed.length ? `FAIL: ${failed.length} of ${total} cases failed` : `PASS: ${total} cases; screenshots in ${path.relative(repo, shots)}/`);
  process.exit(failed.length ? 1 : 0);
}
