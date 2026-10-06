import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  build: { outDir: fileURLToPath(new URL("../../dist/web", import.meta.url)), emptyOutDir: true },
  server: { proxy: { "/v1": "http://127.0.0.1:8787", "/health": "http://127.0.0.1:8787" } },
});
