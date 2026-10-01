import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The editor API is the same local Python process that owns project state. Proxying in dev
// keeps the browser on one origin, so the Server-Sent Events stream and range requests for
// proxy media behave exactly as they do in the built application.
const API = process.env.TAKEONE_EDITOR_API ?? "http://127.0.0.1:8767";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5178,
    strictPort: true,
    proxy: {
      "/api/editor": { target: API, changeOrigin: false, ws: false, timeout: 0 },
    },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: true },
});
