import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Em desenvolvimento (npm run dev) as chamadas à API e o WebSocket vão para o
// backend em http://localhost:8000. Em produção o Caddy serve o build e faz o mesmo.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const api = ((globalThis as any).process?.env?.VITE_API_TARGET as string | undefined) ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: api, ws: true },
      "/health": api,
    },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
});
