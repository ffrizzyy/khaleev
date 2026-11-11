import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// SPEC: single process model. `vite dev` proxies every /api call to the local
// FastAPI server so the browser only ever talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
