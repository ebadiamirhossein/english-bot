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

/**
 * #114 — every helper the service worker CALLS is DEFINED in it.
 *
 * The production console (2026-08-25, and again 2026-09-26 on
 * `app.foundgrant.com`): `ReferenceError: _async_to_generator is not defined
 * at Object.cacheWillUpdate (sw.js)`. **The cause, read from the build:**
 * Next loads `next.config.ts` through SWC with `jsc.target: 'es5'` and a
 * require hook that also transpiles the `.cjs` it imports — so next-pwa's
 * start-URL plugin, a native `async` arrow in its own dist, becomes a call to
 * `_async_to_generator` / `_ts_generator`, helpers defined at the top of THAT
 * module. Workbox copies the plugin into `sw.js` by its source text, and the
 * helpers stay behind. An SWC helper, not Babel's.
 *
 * **POSITIVE CONTROLS FIRST:** the detector finds the exact shape of the
 * defect in a string, and `sw.js` has routes to read at all.
 *
 * **RED DEMONSTRATION (2026-09-26):** on the build before `dynamicStartUrl:
 * false` → red, `["_async_to_generator", "_ts_generator"]`.
 */
function calledButUndefined(source: string): string[] {
  const called = new Set([...source.matchAll(/\b(_[a-z]+(?:_[a-z]+)+)\s*\(/g)].map((m) => m[1]));
  return [...called]
    .filter((name) => !new RegExp(`function ${name}\\b|\\b${name}\\s*=`).test(source))
    .sort();
}

test("every helper the service worker calls is defined in it (#114)", async ({}, info) => {
  test.skip(info.project.name !== "desktop-light", "build output — checked once");
  expect(
    calledButUndefined("{cacheWillUpdate:function(e){return _async_to_generator(function(){})()}}"),
    "the detector cannot see the defect it exists for",
  ).toEqual(["_async_to_generator"]);
  expect(calledButUndefined("function _defined(){} _defined_too=1; _defined_too()")).toEqual([]);

  const sw = readFileSync(path.join(__dirname, "..", "public", "sw.js"), "utf-8");
  expect(sw, "no route in sw.js — this check is reading nothing").toContain("registerRoute(");
  expect(calledButUndefined(sw)).toEqual([]);
});
