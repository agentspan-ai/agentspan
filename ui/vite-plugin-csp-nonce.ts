import type { Plugin } from "vite";

/**
 * Placeholder nonce value that MUST be replaced at deploy time by the server
 * or reverse proxy with a cryptographically random, per-response nonce.
 *
 * Example nginx config:
 *   sub_filter '__CSP_NONCE_PLACEHOLDER__' '$request_id';
 *   sub_filter_once off;
 *   add_header Content-Security-Policy "script-src 'nonce-$request_id'";
 */
const NONCE_PLACEHOLDER = "__CSP_NONCE_PLACEHOLDER__";

/**
 * Vite plugin to add CSP nonce placeholders to all script tags in the built HTML.
 * The placeholder must be replaced with a real per-request nonce at serve time.
 */
export function vitePluginCspNonce(): Plugin {
  return {
    name: "vite-plugin-csp-nonce",
    enforce: "post",
    transformIndexHtml(html) {
      // Add nonce placeholder to all script tags that don't already have one
      return html.replace(
        /<script(?![^>]*\snonce=)([^>]*)>/gi,
        `<script nonce="${NONCE_PLACEHOLDER}"$1>`,
      );
    },
  };
}
