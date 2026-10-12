/**
 * Development-only gallery. It is not referenced by `pnpm build`, so it can never
 * reach a production bundle; `pnpm gallery` serves it locally.
 */
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  server: { port: Number(process.env["E_AGENT_GALLERY_PORT"] ?? 8793) },
});
