import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

// `just dash` serves the API on 127.0.0.1:4700; `just web-dev` proxies to it.
const API_PORT = process.env.PORT ?? "4700";
const API_TARGET = `http://127.0.0.1:${API_PORT}`;

// Node 25+ has its own global localStorage; without --localstorage-file it is undefined
// and hides happy-dom's. Older Node does not know the flag.
const NODE_MAJOR = Number(process.versions.node.split(".")[0]);
const TEST_EXEC_ARGV = NODE_MAJOR >= 25 ? ["--no-experimental-webstorage"] : [];

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 4701,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        // The API rejects writes whose Origin is not its own host (cross_origin).
        headers: { Origin: API_TARGET },
      },
    },
  },
  build: {
    // Packaged with aifactory so `factory obs` runs without Node.
    outDir: fileURLToPath(new URL("../src/aifactory/web/static", import.meta.url)),
    emptyOutDir: true,
  },
  test: {
    environment: "happy-dom",
    // worker threads start faster than forked processes: 78 s -> 63 s for the whole suite
    pool: "threads",
    poolOptions: { threads: { execArgv: TEST_EXEC_ARGV } },
    include: ["src/**/*.test.ts"],
    // every test starts on #/r/haifa/backlog: repo-scoped requests go to /api/repos/haifa/…
    setupFiles: ["src/test/setup.ts"],
  },
});
