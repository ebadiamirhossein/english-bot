import { defineConfig, type Project } from "@playwright/test";

/**
 * W16a — the repository's first browser harness (CLAUDE.md §3a).
 *
 * **WHAT IT PROVES AND WHAT IT CANNOT, IN WORDS, SO THE BOUNDARY IS NOT DROPPED
 * LATER.** It proves a control is on screen, unclipped and reachable at a given
 * size and theme. **It cannot judge whether the screen is good, whether a
 * correction teaches, or whether an opening line is true** — and it cannot raise
 * a software keyboard: `phone-keyboard-*` proves the column of three at the
 * height a keyboard leaves (design `1j`: 812 − 44 status − 291 keyboard), not how
 * iOS Safari behaves with one. The operator's phone check owns that (#407).
 *
 * **NO BACKEND, NO DATABASE, NO PROVIDER, NO BILLED CALL.** Every request to the
 * API origin is answered by `page.route` from `components/write/write.fixture.json`,
 * which Python generates through the real serialisers (#190). Nothing here runs a
 * production entrypoint (§5b).
 *
 * **A PRODUCTION BUILD, NOT `next dev`**: the checks run on the CSS a learner
 * gets, with no dev overlay. The service worker is blocked so it cannot answer a
 * request the route should.
 *
 * **NO CI. It runs by hand:** by Claude Code before the `BUILD_PROGRESS.md`
 * update in every slice that touches a screen, and by the operator before any
 * screen-changing Vercel rebuild — `pnpm test:e2e`.
 */

export const API = "http://api.e2e.test";
// W24c: overridable, because a port another local project holds made a run
// race two servers (2026-09-27). The default is unchanged.
const PORT = Number(process.env.E2E_PORT ?? 3100);

const phone = { width: 390, height: 768 }; // 812 − 44 status bar
const keyboard = { width: 390, height: 477 }; // 768 − 291 keyboard (`1j`)
const desktop = { width: 1280, height: 800 };

const projects: Project[] = [];
for (const scheme of ["light", "dark"] as const) {
  projects.push(
    { name: `phone-${scheme}`, use: { browserName: "webkit", viewport: phone, colorScheme: scheme, hasTouch: true } },
    { name: `phone-keyboard-${scheme}`, use: { browserName: "webkit", viewport: keyboard, colorScheme: scheme, hasTouch: true } },
    { name: `desktop-${scheme}`, use: { browserName: "chromium", viewport: desktop, colorScheme: scheme } },
  );
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: true,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    serviceWorkers: "block",
    trace: "off",
  },
  webServer: {
    command: `pnpm build && pnpm exec next start -p ${PORT} -H 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: false,
    timeout: 300_000,
    env: { NEXT_PUBLIC_API_URL: API },
  },
  projects,
});
