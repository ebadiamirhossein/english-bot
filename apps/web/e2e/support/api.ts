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

/**
 * W17 — block 3 with weak-spot drills, from `components/session/drill.fixture.json`
 * (`scripts/export_drill_fixture.py`, held to the wire by
 * `tests/test_drill_fixture.py`).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const drillFixture: Record<string, any> = JSON.parse(
  readFileSync(path.join(__dirname, "../../components/session/drill.fixture.json"), "utf-8"),
);

export async function mockApi(
  page: Page,
  {
    today = fixture.today,
    correct = { body: fixture.two } as CorrectReply,
    session = fixture.session,
    answer = undefined as unknown,
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
  if (answer !== undefined) {
    // W17 — `POST /items/{id}/answer`, from the drill fixture.
    await page.route(`${API}/items/*/answer`, (route) =>
      route.request().method() === "OPTIONS"
        ? route.fulfill({ status: 204, headers: cors(route) })
        : json(route, 200, answer),
    );
  }
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

/**
 * W15 — `/talk` and its two rungs, from `components/session/talk.fixture.json`
 * (`scripts/export_talk_fixture.py`, held to the wire by `tests/test_talk_fixture.py`).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const talkFixture: Record<string, any> = JSON.parse(
  readFileSync(path.join(__dirname, "../../components/session/talk.fixture.json"), "utf-8"),
);

/**
 * Answers every `/conversation/*` call from the talk fixture. Call AFTER
 * `mockApi` (a later `page.route` wins). `kind` picks the rung the open, turn
 * and close answer as; `talk` answers as a conversation.
 */
export async function mockTalk(
  page: Page,
  {
    rungs = talkFixture.rungs_both,
    kind = "answer" as "talk" | "answer" | "retell",
    close = undefined as unknown,
  } = {},
) {
  const bodies: Record<string, unknown> = {
    "/conversation/rungs": rungs,
    "/conversation/topics": talkFixture.topics,
    "/conversation/open":
      kind === "talk" ? talkFixture.open_talk : kind === "answer" ? talkFixture.open_answer : talkFixture.open_retell,
    "/conversation/turn": kind === "talk" ? talkFixture.turn_talk : talkFixture.turn_rung,
    "/conversation/close":
      close ?? (kind === "retell" ? talkFixture.close_retell : talkFixture.close_answer),
    "/conversation/save-word": { state: "saved" },
  };
  for (const [route, body] of Object.entries(bodies)) {
    await page.route(`${API}${route}`, (r) =>
      r.request().method() === "OPTIONS"
        ? r.fulfill({ status: 204, headers: cors(r) })
        : json(r, 200, body),
    );
  }
}

/**
 * W19 — `/progress`, from `components/progress/progress.fixture.json`
 * (`scripts/export_progress_fixture.py`, held to the wire by
 * `tests/test_progress_fixture.py`).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const progressFixture: Record<string, any> = JSON.parse(
  readFileSync(path.join(__dirname, "../../components/progress/progress.fixture.json"), "utf-8"),
);

/**
 * Answers `GET /progress` with ``body``, or with a 500 when ``status`` is
 * given. Call AFTER `mockApi` (a later `page.route` wins).
 */
export async function mockProgress(
  page: Page,
  { body = progressFixture.weeks_in as unknown, status = 200 } = {},
) {
  await page.route(`${API}/progress`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, status, status === 200 ? body : { detail: "x" }),
  );
}

/**
 * W20 — `/push/*`, from `components/push/push.fixture.json`
 * (`scripts/export_push_fixture.py`: the real `GET /push/key` route and the
 * `PushStateOut` / `PushSubscriptionIn` schemas, #190).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const pushFixture: Record<string, any> = JSON.parse(
  readFileSync(path.join(__dirname, "../../components/push/push.fixture.json"), "utf-8"),
);

/** What the page posted to `/push/*`, in order: the path and the parsed body. */
export type PushCall = { url: string; body: unknown };

/**
 * Answers the four push routes. Call AFTER `mockApi` (a later `page.route`
 * wins). `on` is what `/push/state` says; `subscribe` can be held (the working
 * state) or failed (the trouble state). Returns the calls made, so a test can
 * read what the endpoint travelled in.
 */
export async function mockPush(
  page: Page,
  {
    key = pushFixture.key_set as unknown,
    on = false,
    subscribe = { body: pushFixture.on } as CorrectReply,
  } = {},
) {
  const calls: PushCall[] = [];
  const answer = (body: unknown) => async (route: Route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors(route) });
      return;
    }
    calls.push({ url: route.request().url(), body: route.request().postDataJSON() });
    await json(route, 200, body);
  };
  await page.route(`${API}/push/key`, (route) => json(route, 200, key));
  await page.route(`${API}/push/state`, answer(on ? pushFixture.on : pushFixture.off));
  await page.route(`${API}/push/unsubscribe`, answer(pushFixture.off));
  await page.route(`${API}/push/subscribe`, async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors(route) });
      return;
    }
    calls.push({ url: route.request().url(), body: route.request().postDataJSON() });
    if ("status" in subscribe) {
      await json(route, subscribe.status, { detail: "x" });
      return;
    }
    if ("hold" in subscribe) await subscribe.hold;
    await json(route, 200, subscribe.body);
  });
  return calls;
}

/**
 * W18 — `/placement/*`, from `components/placement/placement.fixture.json`
 * (`scripts/export_placement_fixture.py`, held to the wire by
 * `tests/test_placement_fixture.py`).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const placementFixture: Record<string, any> = JSON.parse(
  readFileSync(path.join(__dirname, "../../components/placement/placement.fixture.json"), "utf-8"),
);

/** What the page posted to `/placement/*`: the path and the parsed body. */
export type PlacementCall = { url: string; body: unknown };

/**
 * Answers the placement routes. Call AFTER `mockApi`. `answers` is the queue
 * of steps `POST /placement/answer` returns, one per call (the last repeats).
 * The clip route answers a few silent bytes. Returns every call made.
 */
export async function mockPlacement(
  page: Page,
  {
    overview = placementFixture.ready as unknown,
    start = placementFixture.steps.vocabulary as unknown,
    answers = [placementFixture.steps.vocabulary] as unknown[],
    finish = placementFixture.result_first as unknown,
  } = {},
) {
  const calls: PlacementCall[] = [];
  let next = 0;
  const post = (reply: () => unknown) => async (route: Route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: cors(route) });
      return;
    }
    calls.push({ url: route.request().url(), body: route.request().postDataJSON() });
    await json(route, 200, reply());
  };
  await page.route(`${API}/placement`, (route) => json(route, 200, overview));
  await page.route(`${API}/placement/start`, post(() => start));
  await page.route(
    `${API}/placement/answer`,
    post(() => answers[Math.min(next++, answers.length - 1)]),
  );
  await page.route(`${API}/placement/finish`, post(() => finish));
  await page.route(`${API}/placement/items/*/audio`, (route) =>
    route.fulfill({ status: 200, contentType: "audio/mpeg", headers: cors(route), body: Buffer.alloc(8) }),
  );
  return calls;
}

/**
 * W23 — `GET /admin/activity`, from `components/admin/admin.fixture.json`
 * (`scripts/export_admin_fixture.py`, held to the wire by
 * `tests/test_admin_fixture.py`).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const adminFixture: Record<string, any> = JSON.parse(
  readFileSync(path.join(__dirname, "../../components/admin/admin.fixture.json"), "utf-8"),
);

/**
 * Answers `GET /admin/activity` with ``body``, or with ``status`` (404 for a
 * learner who is not the operator, 500 for a failed load). Call AFTER `mockApi`.
 */
export async function mockAdmin(
  page: Page,
  { body = adminFixture.two as unknown, status = 200 } = {},
) {
  await page.route(`${API}/admin/activity`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, status, status === 200 ? body : { detail: status === 404 ? "not_found" : "x" }),
  );
}
