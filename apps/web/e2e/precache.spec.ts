import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

/**
 * W23 — the Sentry SDK is a lazy chunk, and it must stay out of the service
 * worker's precache (`next.config.ts`'s `exclude`). Precached, every learner's
 * phone would download it on install while monitoring is off.
 *
 * Reads the production build the harness's web server just made (`.next/` and
 * the generated `public/sw.js`) — which is why it lives here and not in Vitest.
 * Build output is the same for every project, so it runs once.
 *
 * **POSITIVE CONTROL FIRST:** the SDK chunks are found before their absence is
 * asserted. Without it, a build that stopped emitting the marker would make
 * "none of them is precached" pass by finding none.
 *
 * **RED DEMONSTRATION (2026-09-25):** the `exclude` function removed from
 * `next.config.ts` → red (both SDK chunks listed in `sw.js`).
 */
test("the Sentry SDK chunks are built but not precached", async ({}, info) => {
  test.skip(info.project.name !== "desktop-light", "build output — checked once");
  const chunks = path.join(__dirname, "..", ".next", "static", "chunks");
  const sdk = readdirSync(chunks)
    .filter((name) => name.endsWith(".js"))
    .filter((name) => readFileSync(path.join(chunks, name), "utf-8").includes("sentry.javascript"));
  expect(sdk.length, "no chunk carries the SDK — the marker moved").toBeGreaterThan(0);

  const sw = readFileSync(path.join(__dirname, "..", "public", "sw.js"), "utf-8");
  expect(sw, "the precache manifest is empty — this check is reading nothing").toContain("static/chunks/");
  for (const name of sdk) expect(sw).not.toContain(name);
});
