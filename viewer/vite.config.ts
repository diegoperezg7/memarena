import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built assets go straight into the Python package so the wheel ships the viewer.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../src/memarena/viewer_dist",
    emptyOutDir: true,
    assetsDir: "assets",
  },
});
