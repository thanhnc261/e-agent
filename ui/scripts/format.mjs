/**
 * Scoped Prettier runner. Formatting is migrated per module, so the authored scope
 * lives in `.prettierscope` instead of reformatting the whole repository at once.
 *
 *   node scripts/format.mjs --check        # gate the migrated scope
 *   node scripts/format.mjs --write        # format the migrated scope
 *   node scripts/format.mjs --write path…  # format explicit paths (adding a module)
 */
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const uiRoot = fileURLToPath(new URL("..", import.meta.url));
const argv = process.argv.slice(2);
const mode = argv.find(a => a === "--check" || a === "--write") ?? "--check";
const explicit = argv.filter(a => !a.startsWith("--"));

const scope = explicit.length
  ? explicit
  : readFileSync(new URL("../.prettierscope", import.meta.url), "utf8")
      .split("\n")
      .map(line => line.trim())
      .filter(line => line && !line.startsWith("#"));

if (scope.length === 0) {
  console.log("No paths in formatting scope; nothing to do.");
  process.exit(0);
}

const result = spawnSync("prettier", [mode, ...scope], { cwd: uiRoot, stdio: "inherit", shell: false });
if (result.error) {
  console.error(`prettier could not be started: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
