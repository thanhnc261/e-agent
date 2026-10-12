/**
 * Member discovery views (enterprise overlay adoption plan FE-06, ADR 0017).
 * Provider metadata drives the cards with no UI source change; health stays unknown;
 * a revoked connection is visibly unusable; and nothing offers to connect, grant or
 * repair access. A workspace without these read models shows no section at all.
 */
import { expect, test } from "@playwright/test";
import { MockApi } from "../src/index.ts";

test("catalog and connection cards come from server metadata alone", async ({ page }) => {
  const api = new MockApi();
  (api.connections!["connections"] as Record<string, unknown>[])[0]!["integration_id"] = "records-system";
  (api.catalog!["templates"] as Record<string, unknown>[])[0]!["title"] = "renamed by the server";
  await api.install(page);
  await page.goto("/#/connections");

  await expect(page.getByTestId("task-catalog")).toBeVisible();
  const templates = page.getByTestId("catalog-template");
  await expect(templates).toHaveCount(2);
  await expect(templates.nth(0)).toContainText("renamed by the server");
  await expect(templates.nth(0)).toHaveAttribute("data-available", "true");
  await expect(templates.nth(1)).toHaveAttribute("data-available", "false");
  await expect(page.getByTestId("catalog-reason").first()).toContainText("No connection you can use");

  const cards = page.getByTestId("connection");
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText("records-system");
  // Health is never asserted from a read model, and an undisclosed identity stays so.
  await expect(page.getByTestId("connection-health").first()).toContainText("Unknown");
  await expect(page.getByTestId("connection-identity").nth(1)).toContainText("Not disclosed");
  await expect(cards.nth(1)).toHaveAttribute("data-status", "revoked");
  await expect(cards.nth(1)).toContainText("Revoked");
});

test("the connection view offers no credential or connect control", async ({ page }) => {
  await new MockApi().install(page);
  await page.goto("/#/connections");
  await expect(page.getByTestId("connections")).toBeVisible();
  // The only interactive elements are disclosure toggles: no action control exists,
  // so nothing here can be mistaken for a request that grants access.
  const view = page.getByTestId("connections");
  expect(await view.locator("button, input, select, textarea, a[href]").count()).toBe(0);
  expect(await view.locator("summary").count()).toBeGreaterThan(0);
  const text = (await view.innerText()).toLowerCase();
  for (const forbidden of ["api key", "secret", "password", "sign in", "client id"]) {
    expect(text.includes(forbidden), forbidden).toBe(false);
  }
  await expect(view).toContainText("administrative operations and are not available here");
});

test("a workspace without these read models shows no section and no empty list", async ({ page }) => {
  const api = new MockApi();
  api.connections = null;
  api.catalog = null;
  await api.install(page);
  await page.goto("/");
  await expect(page.getByTestId("section-connections")).toHaveCount(0);
  await expect(page.getByTestId("task-catalog")).toHaveCount(0);

  await page.goto("/#/connections");
  // The honest static statement stands in; it never claims an empty catalog.
  await expect(page.getByTestId("installed-scope")).toBeVisible();
  await expect(page.getByTestId("connections-status")).toHaveAttribute("data-state", "unsupported");
  await expect(page.getByTestId("connections-empty")).toHaveCount(0);
});

test("a denied projection is not shown as an empty one", async ({ page }) => {
  const api = new MockApi();
  api.connections = null;
  api.discoveryStatus = 404;
  await api.install(page);
  await page.route("**/v1/me/connections", route =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ code: "FORBIDDEN", message: "not available" }),
    }),
  );
  await page.goto("/#/connections");
  await expect(page.getByTestId("connections-status")).toHaveAttribute("data-state", "denied");
  await expect(page.getByTestId("connections-empty")).toHaveCount(0);
  await expect(page.getByTestId("connection")).toHaveCount(0);
});

test("an empty inventory reads as empty, not as missing", async ({ page }) => {
  const api = new MockApi();
  api.connections = { schema_version: "1", observed_at: "2026-10-09T00:00:00Z", connections: [] };
  await api.install(page);
  await page.goto("/#/connections");
  await expect(page.getByTestId("connections-empty")).toBeVisible();
  await expect(page.getByTestId("connections-status")).toHaveCount(0);
});

test("an unreadable version is reported instead of rendered", async ({ page }) => {
  const api = new MockApi();
  api.catalog = { schema_version: "7", templates: [{ template_id: "x", availability: "available" }] };
  await api.install(page);
  await page.goto("/#/connections");
  await expect(page.getByTestId("installed-scope")).toBeVisible();
  await expect(page.getByTestId("catalog-template")).toHaveCount(0);
});

test("a payload that claims a readable version but is not reports itself", async ({ page }) => {
  const api = new MockApi();
  // Declares schema 1 but omits the collection schema 1 defines.
  api.connections = { schema_version: "1", observed_at: "2026-10-09T00:00:00Z" };
  await api.install(page);
  await page.goto("/#/connections");
  await expect(page.getByTestId("connections-status")).toHaveAttribute("data-state", "malformed");
  // Malformed is never shown as an empty inventory.
  await expect(page.getByTestId("connections-empty")).toHaveCount(0);
  await expect(page.getByTestId("connection")).toHaveCount(0);
  await expect(page.getByTestId("connections-status")).toContainText("could not be read");
});

test("one malformed entry does not shrink an inventory into an apparently complete one", async ({ page }) => {
  const api = new MockApi();
  const entries = api.connections!["connections"] as Record<string, unknown>[];
  delete entries[1]!["revision"];
  await api.install(page);
  await page.goto("/#/connections");
  await expect(page.getByTestId("connections-status")).toHaveAttribute("data-state", "malformed");
  // The one good entry is not presented as the whole inventory.
  await expect(page.getByTestId("connection")).toHaveCount(0);
});
