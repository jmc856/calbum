import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // No custom domain, so GitHub Pages serves this as a project page at
  // jmc856.github.io/calbum/, not at the origin root. Without this, every
  // built asset URL resolves to /assets/... instead of /calbum/assets/...
  // and 404s. Revisit if a custom domain is added later (base: "/").
  base: "/calbum/",
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false },
});
