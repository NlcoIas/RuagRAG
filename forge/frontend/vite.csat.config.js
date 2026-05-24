import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "forge-compat",
      transformIndexHtml(html) {
        return html.replace(/ crossorigin/g, "");
      },
    },
  ],
  base: "./",
  build: {
    outDir: "../static/csat",
    emptyOutDir: true,
    modulePreload: false,
    rollupOptions: {
      input: resolve(__dirname, "csat.html"),
    },
  },
});
