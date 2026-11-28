// Vite build and dev-server settings for the Steward web UI.
// In development, every /steward/* request is forwarded to the Steward API,
// so the browser only ever talks to one address (no CORS needed).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.STEWARD_API_URL || "http://127.0.0.1:7777";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/steward": { target: apiTarget, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.js"],
  },
});
