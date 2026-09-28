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

/**
 * **W31a (#465): the mocks refuse what FastAPI refuses.** A string body sent
 * with no `Content-Type` leaves the browser as `text/plain;charset=UTF-8`, and
 * the API answers 422 without running the route. `saveWord` did exactly that for
 * sixteen taps on production while this harness answered 200, because it never
 * looked at the header. Every mocked body goes through `json()`, so the check
 * lives here. A recording (`audio/*`) is not text and passes.
 */
function fastApiWouldRefuse(route: Route): boolean {
  const request = route.request();
  if (!request.postData()) return false;
  const type = (request.headers()["content-type"] ?? "").toLowerCase();
  return type === "" || type.startsWith("text/plain");
}

async function json(route: Route, status: number, body: unknown) {
  if (fastApiWouldRefuse(route)) {
    await route.fulfill({
      status: 422,
      contentType: "application/json",
      headers: cors(route),
      body: JSON.stringify({
        detail: [{ type: "model_attributes_type", loc: ["body"], msg: "not JSON" }],
      }),
    });
    return;
  }
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

/**
 * W13d — `/review` with a picturable word, from
 * `components/cards/review-queue.fixture.json` (`scripts/export_review_fixture.py`,
 * held to the wire by `tests/test_lexeme_images.py`). The picture's bytes are
 * `e2e/fixtures/card-picture.png`, this project's own drawing, written by the
 * same script.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const reviewFixture: Record<string, any> = JSON.parse(
  readFileSync(path.join(__dirname, "../../components/cards/review-queue.fixture.json"), "utf-8"),
);

const cardPicture = readFileSync(path.join(__dirname, "../fixtures/card-picture.png"));

export async function mockReview(
  page: Page,
  { queue = reviewFixture as unknown, picture = "ok" as "ok" | "offline" } = {},
) {
  const pictureRequests: string[] = [];
  await page.route(`${API}/review/queue*`, (route) => json(route, 200, queue));
  await page.route(`${API}/lexeme-images/**`, async (route) => {
    pictureRequests.push(route.request().url());
    if (picture === "offline") {
      await route.abort("internetdisconnected");
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      headers: { ...cors(route), "cache-control": "private, max-age=31536000, immutable" },
      body: cardPicture,
    });
  });
  return pictureRequests;
}

/**
 * W24e — keep going: `GET /keep-going`, `POST /keep-going/watch` and, for the
 * Sunday home, `GET /week` — every body from `write.fixture.json` (the real
 * serialisers, #190). `watch: null` answers the POST with the real 404.
 * YouTube itself is refused so no test reaches the network.
 */
export async function mockKeepGoing(
  page: Page,
  {
    options = fixture.keep_going_weekday,
    watch = fixture.watch as unknown,
    week = undefined as unknown,
    /**
     * W32f — what `GET /keep-going/watch` (the nav's Watch, today's video)
     * answers; `null` is its 404. Defaults to `watch`, so every spec written
     * before W32f sees the same video through either door.
     */
    today = undefined as unknown,
  } = {},
) {
  /** The methods `/keep-going/watch` was called with — the nav must GET. */
  const methods: string[] = [];
  await page.route(/youtube(-nocookie)?\.com|ytimg\.com/, (route) => route.abort());
  await page.route(`${API}/keep-going`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, 200, options),
  );
  await page.route(`${API}/keep-going/watch`, (route) => {
    const method = route.request().method();
    if (method === "OPTIONS") return route.fulfill({ status: 204, headers: cors(route) });
    methods.push(method);
    const body = method === "GET" && today !== undefined ? today : watch;
    return body === null
      ? json(route, 404, { detail: method === "GET" ? "nothing_today" : "nothing_to_watch" })
      : json(route, 200, body);
  });
  if (week !== undefined) {
    await page.route(`${API}/week`, (route) => json(route, 200, week));
  }
  return methods;
}

/**
 * W31b — the video routes the study screen calls: the progress ping and the
 * word tap. Returns the save-word requests it saw, so a spec can assert what
 * the web actually sent (#465). `saveState` is the body's `state`.
 */
export async function mockVideo(
  page: Page,
  {
    save = fixture.save_pending_soon as unknown,
    lookup = fixture.word_lookup_meaning as unknown,
    /** W32b: the meanings map. Absent → the catch-all 404, so the page takes
     * the sheet's fallback (per-word lookup) — W31c's specs run unchanged. */
    meanings = undefined as unknown,
  } = {},
) {
  const saves: { contentType: string; body: unknown }[] = [];
  if (meanings !== undefined) {
    await page.route(`${API}/video/*/meanings`, (route) =>
      route.request().method() === "OPTIONS"
        ? route.fulfill({ status: 204, headers: cors(route) })
        : json(route, 200, meanings),
    );
  }
  // W31c — the word sheet's read, from `write.fixture.json` (the real model).
  await page.route(`${API}/video/*/word?*`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, 200, lookup),
  );
  await page.route(`${API}/video/*/progress`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, 200, {
          video_id: 44, youtube_id: "aqz-KE-bpKQ", title: null, duration_s: 48,
          resume_position_s: 0, completed: false,
        }),
  );
  await page.route(`${API}/video/*/save-word`, (route) => {
    if (route.request().method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: cors(route) });
    }
    saves.push({
      contentType: route.request().headers()["content-type"] ?? "",
      body: route.request().postDataJSON(),
    });
    return json(route, 200, save);
  });
  return saves;
}

/**
 * W32c — `POST /video/{id}/word/define`, the miss lookup, answered with
 * `body` after `delayMs` (so the sheet's *Looking it up…* can be seen). Returns
 * the request bodies it saw — the word and the line's index, never its text.
 */
export async function mockDefine(page: Page, body: unknown, delayMs = 0) {
  const asked: unknown[] = [];
  await page.route(`${API}/video/*/word/define`, async (route) => {
    if (route.request().method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: cors(route) });
    }
    asked.push(route.request().postDataJSON());
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
    return json(route, 200, body);
  });
  return asked;
}

/** W31c — `GET /words`, My words, from `write.fixture.json`. */
export async function mockMyWords(page: Page, body: unknown = fixture.my_words) {
  await page.route(`${API}/words*`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, 200, body),
  );
}

/**
 * A stand-in for the YouTube IFrame API, installed before the page loads. It
 * behaves like the real one where the player depends on it: the constructor
 * replaces the element it is given, the methods answer only after `onReady`
 * fires (asynchronously), and time, state, seeks, pauses and plays are read and
 * set through `window.__yt`.
 */
export async function fakeYouTube(
  page: Page,
  {
    /**
     * W32e — YouTube's own captions module, which the IFrame API has but does
     * not document. `absent`: no `unloadModule`/`getOption` at all (every spec
     * before W32e). `on`: a viewer's saved caption preference — a track is
     * active, and `unloadModule('captions')` turns it off. `stuck`: the same
     * track, and unloading it does nothing (the case the hint is for).
     */
    captions = "absent" as "absent" | "on" | "stuck",
  } = {},
) {
  await page.addInitScript((captions) => {
    const yt = {
      time: 0, state: 2, options: null as unknown, seeks: [] as number[], pauses: 0, plays: 0,
      unloaded: [] as string[],
      track: (captions === "absent" ? {} : { languageCode: "en" }) as Record<string, unknown>,
      /** W32f — set the state and tell the page, as YouTube's
       * `onStateChange` does (the captions poll runs only while playing). */
      setState(state: number) {
        yt.state = state;
        (yt.options as { events?: { onStateChange?: (e: { data: number }) => void } } | null)
          ?.events?.onStateChange?.({ data: state });
      },
    };
    (window as unknown as { __yt: typeof yt }).__yt = yt;
    const captionsModule =
      captions === "absent"
        ? {}
        : {
            unloadModule(name: string) {
              yt.unloaded.push(name);
              if (name === "captions" && captions === "on") yt.track = {};
            },
            getOption(name: string, key: string) {
              return name === "captions" && key === "track" ? yt.track : undefined;
            },
          };
    (window as unknown as { YT: unknown }).YT = {
      Player: class {
        constructor(el: HTMLElement, options: { events?: { onReady?: (e: unknown) => void } }) {
          Object.assign(this, captionsModule);
          yt.options = options;
          const frame = document.createElement("div");
          frame.setAttribute("data-testid", "fake-yt");
          frame.style.cssText =
            "width:100%;height:100%;background:#1f2937;color:#e5e7eb;display:flex;" +
            "align-items:center;justify-content:center;font:14px system-ui";
          frame.textContent = "▶ video";
          el.replaceWith(frame);
          setTimeout(() => options.events?.onReady?.({ target: this }), 30);
        }
        getCurrentTime() { return yt.time; }
        setPlaybackRate() {}
        destroy() {}
        pauseVideo() { yt.pauses += 1; yt.setState(2); }
        playVideo() { yt.plays += 1; yt.setState(1); }
        seekTo(seconds: number) { yt.seeks.push(seconds); yt.time = seconds; }
        getPlayerState() { return yt.state; }
      },
    };
  }, captions);
}

/**
 * W31d — the word drill: `POST /practice/start`, `POST /practice/answer` and the
 * word's audio, from `write.fixture.json`. Returns the answers it saw.
 */
export async function mockPractice(
  page: Page,
  {
    start = fixture.practice_start as unknown,
    outcome = fixture.practice_right as unknown,
    /** False: every picture's bytes 404, as offline — the drill must say so. */
    pictures = true,
  } = {},
) {
  const answers: unknown[] = [];
  await page.route(`${API}/practice/start`, (route) =>
    route.request().method() === "OPTIONS"
      ? route.fulfill({ status: 204, headers: cors(route) })
      : json(route, 200, start),
  );
  await page.route(`${API}/practice/answer`, (route) => {
    if (route.request().method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: cors(route) });
    }
    answers.push(route.request().postDataJSON());
    return json(route, 200, outcome);
  });
  await page.route(`${API}/practice/*/audio`, (route) =>
    route.fulfill({ status: 200, contentType: "audio/mpeg", headers: cors(route), body: Buffer.alloc(8) }),
  );
  await page.route(`${API}/lexeme-images/**`, (route) =>
    pictures
      ? route.fulfill({ status: 200, contentType: "image/png", headers: cors(route), body: PICTURE })
      : route.fulfill({ status: 404, headers: cors(route) }),
  );
  return answers;
}

/** A 120×80 solid PNG: a stand-in picture, so the drill's layout is real. */
const PICTURE = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAHgAAABQCAIAAABd+SbeAAAAqUlEQVR4nO3QAQkAIADAMPsHMIkhjGULhTt4gLMx19aFxvODTwINuhVo0K1Ag24FGnQr0KBbgQbdCjToVqBBtwINuhVo0K1Ag24FGnQr0KBbgQbdCjToVqBBtwINuhVo0K1Ag24FGnQr0KBbgQbdCjToVqBBtwINuhVo0K1Ag24FGnQr0KBbgQbdCjToVqBBtwINuhVo0K1Ag24FGnQr0KBbgQbdCjToVgf8VaeECfwysgAAAABJRU5ErkJggg==", "base64");

