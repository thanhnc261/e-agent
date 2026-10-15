import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env["E_AGENT_UI_PORT"] ?? 8791);
const repoRoot = fileURLToPath(new URL("../../..", import.meta.url));
const FIXTURE_PROFILE = "src/e_agent/plugins/erp/simulator/fixture_profile.json";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1, // the live tests share one fixture server
  retries: 0,
  reporter: process.env["CI"] ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // The server ships no profile; the fixture profile is a resource of the ERP simulator plugin.
    command: `uv run -q e-agent --profile ${FIXTURE_PROFILE} serve --port ${PORT} --static ui/dist/web`,
    cwd: repoRoot,
    url: `http://127.0.0.1:${PORT}/health/ready`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
