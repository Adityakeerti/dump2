import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy mirrors the production Caddy routes (Project/Caddyfile), so the same relative URLs
// work in `npm run dev` and behind the reverse proxy. Override targets with env vars if needed.
const env = (k, d) => process.env[k] || d;
const TWIN = env("TWIN_URL", "http://127.0.0.1:8003");
const CITY = env("CITY_SIM_URL", "http://127.0.0.1:8004");
const AGENT = env("AGENT_URL", "http://127.0.0.1:8000");
const COMPLAINTS = env("COMPLAINT_URL", "http://127.0.0.1:8001");
const EMERGENCY = env("EMERGENCY_URL", "http://127.0.0.1:8002");
const CIVIC = env("CIVIC_SIM_URL", "http://127.0.0.1:8005");

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/twin": { target: TWIN, ws: true, changeOrigin: true },
      "/api/city": { target: CITY, changeOrigin: true },
      "/api/civic": { target: CIVIC, changeOrigin: true },
      "/api/complaint-flow": {
        target: COMPLAINTS,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/complaint-flow\//, "/api/"),
      },
      "/api/emergency": {
        target: EMERGENCY,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/emergency\//, "/api/"),
      },
      "/api/agent": { target: AGENT, changeOrigin: true },
      "/agent": { target: AGENT, changeOrigin: true, rewrite: (p) => p.replace(/^\/agent/, "") },
    },
  },
});
