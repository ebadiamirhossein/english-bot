import withPWAInit from "@ducanh2912/next-pwa";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
};

/**
 * Service worker via Workbox.
 *
 * `@ducanh2912/next-pwa` rather than the original `next-pwa`: the original
 * has not been released since 2022 and declares no support past Next 13,
 * while this fork is the same Workbox setup maintained against Next 14/15.
 * ARCHITECTURE-v3 §2 says "next-pwa / Workbox" — this is that, still built.
 *
 * Disabled in development so a cached shell never hides an edit.
 */
export default withPWAInit({
  dest: "public",
  disable: process.env.NODE_ENV === "development",
  register: true,
  cacheOnFrontEndNav: true,
  reloadOnOnline: true,
  // #114 (2026-09-26): the start-URL route's `cacheWillUpdate` reached `sw.js`
  // calling an SWC helper it does not carry — Next compiles this file, and the
  // `.cjs` it imports, to ES5, and Workbox copies the plugin by its source
  // text. `/` returns one static document in every state (no middleware, no
  // server redirect), which is the case the option documents for `false`;
  // `/` then caches under the default page rule like every other route.
  // `e2e/precache.spec.ts` asserts no undefined helper is called.
  dynamicStartUrl: false,
  workboxOptions: {
    // Skip waiting: with two users there is no staged rollout to protect, and
    // an app that needs closing twice to pick up a fix is worse.
    skipWaiting: true,
    // W23 — keep the Sentry SDK OUT OF THE PRECACHE. It is a lazy chunk that
    // `lib/monitoring.ts` fetches only when a DSN is set; precached, every
    // learner's service worker would download it (~120 kB gzipped, two copies)
    // on install even with monitoring off. Measured 2026-09-25: both copies
    // were in `sw.js`'s manifest before this line.
    //
    // **The first three entries are next-pwa's own defaults**, restated
    // because giving `exclude` at all REPLACES them (read in
    // `@ducanh2912/next-pwa/dist/index.cjs`: `exclude: C = [...]`).
    exclude: [
      /\/_next\/static\/.*(?<!\.p)\.woff2/,
      /\.map$/,
      /^manifest.*\.js$/,
      // Found by content, not name: webpack names these chunks by number.
      // `e2e/precache.spec.ts` holds it — and has a positive control, so a
      // chunk that stopped carrying the marker fails the test, not passes it.
      ({ asset }) =>
        asset.name.startsWith("static/chunks/") &&
        String(asset.source.source()).includes("sentry.javascript"),
    ],
  },
})(nextConfig);
