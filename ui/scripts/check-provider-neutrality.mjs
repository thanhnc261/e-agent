// Provider-neutrality gate (UI architecture §6a): no UI source may name a provider.
// Provider names, icons and form fields reach the UI only as server manifest data.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const DENY = /\b(odoo|bigquery|google|gcp|salesforce|hubspot|netsuite|dynamics ?365|zoho|shopify|quickbooks|xero|sap ?(s\/4|hana|erp)?)\b/i;
const SKIP_DIRS = new Set(["node_modules", "dist", "test-results", "playwright-report"]);
const EXTS = /\.(ts|tsx|js|mjs|cjs|json|css|html|md)$/;
const SELF = "scripts/check-provider-neutrality.mjs";

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* walk(path);
    else if (EXTS.test(name)) yield path;
  }
}

const hits = [];
for (const dir of ["packages", "apps", "scripts"]) {
  for (const file of walk(join(ROOT, dir))) {
    const rel = relative(ROOT, file);
    if (rel === SELF) continue;
    readFileSync(file, "utf8")
      .split("\n")
      .forEach((line, i) => {
        const m = DENY.exec(line);
        if (m) hits.push(`${rel}:${i + 1}: "${m[0]}"`);
      });
  }
}
if (hits.length) {
  console.error(`Provider identifiers found in UI sources:\n${hits.join("\n")}`);
  process.exit(1);
}
console.log("ok  no provider identifiers in ui/");
