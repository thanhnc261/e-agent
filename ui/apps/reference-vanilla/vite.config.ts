import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  base: "/reference/",
  build: { outDir: fileURLToPath(new URL("../../dist/web/reference", import.meta.url)), emptyOutDir: true },
});
