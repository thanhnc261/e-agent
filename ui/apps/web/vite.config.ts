import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const api = process.env["E_AGENT_DEV_API_URL"] ?? "http://127.0.0.1:8787";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  build: { outDir: fileURLToPath(new URL("../../dist/web", import.meta.url)), emptyOutDir: true },
  server: { proxy: { "/v1": api, "/health": api, "/overlay": api, "/reference": api } },
});
