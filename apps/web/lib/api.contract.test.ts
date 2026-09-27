import { readFileSync } from "node:fs";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import contract from "./web-requests.contract.json";
import { getMyWords, lookupWord, request, saveWord } from "./api";

/**
 * W31a — the web half of `web-requests.contract.json`.
 *
 * **Sixteen taps answered 422 on production while every test was green**
 * (2026-09-27). `saveWord` sent a JSON string with no `Content-Type`, the
 * browser labelled it `text/plain;charset=UTF-8`, and FastAPI refused to parse
 * it. `tests/test_web_contract.py` replays each entry through the real API;
 * this file holds the client to the same entry, so the two halves can only
 * agree by both matching the file.
 */

type Entry = (typeof contract)[number];

/**
 * What the browser puts on the wire for a string body with no explicit header.
 * The Fetch standard's default for a `USVString` body — **stated, not
 * assumed away**: a test that read "no header" as "no problem" is how this
 * shipped.
 */
const BROWSER_DEFAULT_FOR_STRING = "text/plain;charset=UTF-8";

function wire(init: RequestInit) {
  const headers = new Headers(init.headers);
  const explicit = headers.get("content-type");
  return {
    method: init.method ?? "GET",
    content_type:
      explicit ?? (typeof init.body === "string" ? BROWSER_DEFAULT_FOR_STRING : null),
    body: typeof init.body === "string" ? JSON.parse(init.body) : (init.body ?? null),
  };
}

function capture() {
  const calls: { url: string; init: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ state: "no_gloss", card_ids: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }),
  );
  return calls;
}

const entry = (name: string): Entry => {
  const found = contract.find((e) => e.name === name);
  if (!found) throw new Error(`no contract entry ${name}`);
  return found;
};

afterEach(() => vi.unstubAllGlobals());

describe("the web sends what the contract says", () => {
  it("save_word: POST, JSON, the word and the line's index — never its text", async () => {
    const calls = capture();
    await saveWord(44, "mastodon", 0);
    const expected = entry("save_word");
    expect(calls).toHaveLength(1);
    expect(calls[0].url.endsWith(expected.path.replace("{video_id}", "44"))).toBe(true);
    expect(wire(calls[0].init)).toEqual({
      method: expected.method,
      content_type: expected.content_type,
      body: expected.body,
    });
  });
  it("word_lookup: GET, the word and the line's index in the query", async () => {
    const calls = capture();
    await lookupWord(44, "mastodon", 0);
    const expected = entry("word_lookup");
    expect(calls[0].url.endsWith(expected.path.replace("{video_id}", "44"))).toBe(true);
    expect(wire(calls[0].init)).toEqual({
      method: expected.method,
      content_type: expected.content_type,
      body: expected.body,
    });
  });

  it("my_words: GET, no query on the first page", async () => {
    const calls = capture();
    await getMyWords();
    const expected = entry("my_words");
    expect(calls[0].url.endsWith(expected.path)).toBe(true);
    expect(wire(calls[0].init).method).toBe("GET");
  });
});

/**
 * **The sweep, so the next call cannot repeat it.** `request()` is the only
 * `fetch` in `api.ts`; if it labels every string body as JSON, no exported
 * function can send one as `text/plain`, whatever its author forgot.
 */
describe("every string body leaves as JSON", () => {
  it("api.ts reaches the network through request() and nowhere else", () => {
    const source = readFileSync(path.join(__dirname, "api.ts"), "utf-8");
    expect(source.match(/\bfetch\(/g)).toHaveLength(1);
  });

  it("request() labels a string body application/json when the caller did not", async () => {
    const calls = capture();
    await request("/any", { method: "POST", body: JSON.stringify({ word: "epoch" }) });
    expect(new Headers(calls[0].init.headers).get("content-type")).toBe(
      "application/json",
    );
  });

  it("request() leaves a caller's own type alone (a recording stays audio)", async () => {
    const calls = capture();
    await request("/any", {
      method: "POST",
      headers: { "Content-Type": "audio/webm" },
      body: new Blob(["x"], { type: "audio/webm" }),
    });
    expect(new Headers(calls[0].init.headers).get("content-type")).toBe("audio/webm");
  });
});
