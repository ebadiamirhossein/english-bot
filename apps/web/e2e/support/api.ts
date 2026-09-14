import { readFileSync } from "node:fs";
import path from "node:path";

import type { Page, Route } from "@playwright/test";

import { API } from "../../playwright.config";

/**
 * The API, answered from the Python-generated fixture. **Nothing here is a
 * hand-written body** — every JSON value comes from
 * `components/write/write.fixture.json`, which `tests/test_write_fixture.py`
 * holds to the real wire (#190).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const fixture: Record<string, any> = JSON.parse(
  readFileSync(path.join(__dirname, "../../components/write/write.fixture.json"), "utf-8"),
);

export type CorrectReply =
  | { body: unknown }
  | { status: number }
  | { hold: Promise<void>; body: unknown };

function cors(route: Route) {
  const origin = route.request().headers()["origin"] ?? "*";
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-credentials": "true",
    "access-control-allow-headers": "content-type, accept",
    "access-control-allow-methods": "GET, POST, OPTIONS",
  };
}

async function json(route: Route, status: number, body: unknown) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: cors(route),
    body: JSON.stringify(body),
  });
}

export async function mockApi(
  page: Page,
  {
    today = fixture.today,
    correct = { body: fixture.two } as CorrectReply,
    session = fixture.session,
  } = {},
) {
  // Registered first, so it matches last: anything unlisted is a quiet 404
  // rather than a request that hangs waiting for a server that is not there.
  await page.route(`${API}/**`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, 404, { detail: "not_found" }),
  );
  await page.route(`${API}/health/auth`, (route) => json(route, 200, fixture.auth));
  await page.route(`${API}/session/today`, (route) => json(route, 200, session));
  // W16b — `POST /write/keep`. The real route's body is `{status}`; the key set is
  // held to the wire by `tests/test_writing_route.py`.
  await page.route(`${API}/write/keep`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, 200, { status: "saved" }),
  );
  await page.route(`${API}/write/today`, (route) => json(route, 200, today));
  await page.route(`${API}/correct`, async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors(route) });
      return;
    }
    if ("status" in correct) {
      await json(route, correct.status, { detail: "x" });
      return;
    }
    if ("hold" in correct) await correct.hold;
    await json(route, 200, correct.body);
  });
}

/** Design `1k`'s entry, as a learner would type it. */
export const ENTRY =
  "Today I go to the dentist in the morning. I was very nervous because last time it hurt a lot, but this time she only clean my teeth and it was fine.";

/** `1g`: well past what the field shows at once, and under the 2,000 ceiling. */
export const LONG = Array.from({ length: 6 }, () =>
  "After that I went to the office and we had a long meeting about the new project, and my colleague explained everything twice because nobody understood the first time.",
).join(" ");

/** W16b — design `1n`'s paragraph, as a learner would type it. */
export const PARAGRAPH =
  "I think is a good idea to move in another country for work, but it depends of the person. My cousin moved to Norway three years ago and now he earn much more money than before. But he told me that he miss his family very much, and in the winter he is alone.";
