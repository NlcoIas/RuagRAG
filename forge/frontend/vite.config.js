import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "forge-compat",
      transformIndexHtml(html) {
        // Remove crossorigin from built output — breaks in Forge's sandboxed iframe
        // Keep type="module" — needed for deferred execution (window.__bridge must be injected first)
        return html.replace(/ crossorigin/g, "");
      },
    },
  ],
  base: "./",
  build: {
    outDir: "../static",
    emptyOutDir: true,
    modulePreload: false,
  },
});
