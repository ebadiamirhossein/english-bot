/// <reference types="vitest" />
import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * The frontend suite. Known issue #67 named W6 as the slice that would bring
 * this in, and W6 is that slice eleven times over.
 *
 * What this covers that a source scan cannot: rendering each of the eleven
 * types from the committed projections, tapping, the typed-input path, and the
 * feedback state machine — in particular that **no verdict appears while the
 * request is in flight**, which is the anti-optimistic-grading assertion and
 * cannot be made by reading a file.
 *
 * `jsdom` has no autocorrect and no iOS zoom, so the keyboard attributes are
 * asserted here and settled for real by a human on a phone.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
  // Tailwind v4's PostCSS plugin is an ESM package Vite's CJS config loader
  // cannot construct, and nothing here renders styles anyway — these tests read
  // the DOM, not the paint. An empty plugin list stops Vite from discovering
  // `postcss.config.mjs` at all.
  css: { postcss: { plugins: [] } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // W20 adds `worker/`: the service worker's own handlers, against a stub scope.
    include: ["{app,components,lib,worker}/**/*.test.{ts,tsx}"],
  },
});
