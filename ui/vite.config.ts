import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { createHash } from "crypto";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";
import { defineConfig, loadEnv, Plugin } from "vite";
import svgr from "vite-plugin-svgr";
import tsconfigPaths from "vite-tsconfig-paths";
import { vitePluginCspNonce } from "./vite-plugin-csp-nonce";

const __dirname = dirname(fileURLToPath(import.meta.url));
const packageDir = __dirname;

// In dev, Vite serves docs.html at /docs because it lives in the project root.
// Hard-refreshing /docs (or /docs/*) in the browser bypasses React Router and
// loads the standalone docs bundle instead of the main app. This plugin
// intercepts those requests early and rewrites them to / so Vite's SPA handler
// serves index.html and React Router takes over.
function docsDevRewritePlugin(): Plugin {
  return {
    name: "docs-dev-rewrite",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (
          req.url === "/docs" ||
          req.url?.startsWith("/docs/") ||
          req.url?.startsWith("/docs?")
        ) {
          req.url = "/";
        }
        next();
      });
    },
  };
}

// Plugin to inject build-time hash into context.js script tag
function contextJsHashPlugin(): Plugin {
  const buildHash = createHash("md5")
    .update(Date.now().toString())
    .update(process.pid?.toString() || "")
    .digest("hex")
    .substring(0, 8);

  return {
    name: "context-js-hash",
    transformIndexHtml(html) {
      return html.replace(
        /<script[^>]*src=["']\/context\.js[^"']*["'][^>]*><\/script>/i,
        `<script src="/context.js?v=${buildHash}"></script>`,
      );
    },
  };
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, packageDir);
  const BASE_URL = env.VITE_PUBLIC_URL || "/";

  // Library build mode - creates npm package
  // Note: Type declarations (dts) disabled due to compatibility issues
  // Run `tsc --emitDeclarationOnly` separately if needed
  if (mode === "lib") {
    return {
      plugins: [react(), tsconfigPaths(), svgr()],
      build: {
        lib: {
          entry: resolve(__dirname, "src/index.ts"),
          name: "ConductorUI",
          fileName: "conductor-ui",
          formats: ["es"] as const,
        },
        rollupOptions: {
          external: [
            "react",
            "react-dom",
            "react/jsx-runtime",
            "react-router",
            "react-router-dom",
            "@mui/material",
            "@mui/icons-material",
            "@mui/system",
            "@mui/x-date-pickers",
            "@emotion/react",
            "@emotion/styled",
          ],
          output: {
            globals: {
              react: "React",
              "react-dom": "ReactDOM",
              "react-router-dom": "ReactRouterDOM",
            },
          },
        },
        sourcemap: true,
      },
    };
  }

  // App build mode - creates standalone OSS application
  return {
    base: BASE_URL,
    plugins: [
      react(),
      tailwindcss(),
      tsconfigPaths(),
      svgr(),
      vitePluginCspNonce(),
      contextJsHashPlugin(),
      docsDevRewritePlugin(),
    ],
    optimizeDeps: {
      include: [
        "@emotion/react",
        "@emotion/styled",
        "@mui/material",
        "@mui/system",
      ],
    },
    define: {
      "process.env": {},
    },
    preview: {
      port: 1234,
    },
    server: {
      port: 1234,
      proxy: {
        "/api": {
          target: env.VITE_WF_SERVER || "http://localhost:6767",
          changeOrigin: true,
        },
        "/swagger-ui": {
          target: env.VITE_WF_SERVER || "http://localhost:6767",
          changeOrigin: true,
        },
        "/api-docs": {
          target: env.VITE_WF_SERVER || "http://localhost:6767",
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/setupTests.ts",
      include: ["src/**/*.test.{js,ts,jsx,tsx}"],
      server: {
        deps: {
          // Force Vitest to process Monaco's ESM through its own pipeline
          // rather than trying to load browser-only bundles in jsdom.
          inline: ["monaco-editor"],
        },
      },
    },
  };
});
