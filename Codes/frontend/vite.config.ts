import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000; in production Caddy serves both on one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_PROXY_TARGET ?? "http://localhost:8000", changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 1600 },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts"] },
} as never);
