import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// One self-contained module script: <script type="module" src=".../e-agent-overlay.js">.
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: fileURLToPath(new URL("../../dist/web/overlay", import.meta.url)),
    emptyOutDir: true,
    minify: true,
    lib: {
      entry: fileURLToPath(new URL("./src/index.tsx", import.meta.url)),
      formats: ["es"],
      fileName: () => "e-agent-overlay.js",
    },
  },
});
