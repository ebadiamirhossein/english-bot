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
  workboxOptions: {
    // Skip waiting: with two users there is no staged rollout to protect, and
    // an app that needs closing twice to pick up a fix is worse.
    skipWaiting: true,
  },
})(nextConfig);
