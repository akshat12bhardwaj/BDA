import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The read-only FastAPI service (Code/api/main.py) runs on 127.0.0.1:8000; the dev and preview servers proxy /api to it.
const proxy = { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: "127.0.0.1", port: 5173, proxy },
  preview: { host: "127.0.0.1", port: 4173, proxy },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], css: false },
});
