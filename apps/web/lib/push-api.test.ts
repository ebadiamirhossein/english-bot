import { afterEach, describe, expect, it, vi } from "vitest";

import fixture from "@/components/push/push.fixture.json";
import { getPushKey, getPushState, subscribePush, unsubscribePush } from "@/lib/api";

/**
 * W20 — the four push calls, at the `fetch` they make.
 *
 * **The endpoint is a capability URL** and must only travel in a JSON body:
 * never a path or a query string, where access logs keep it. Each call is
 * asserted to go through `request<T>` (credentials included, JSON accepted,
 * #398) and to put the endpoint nowhere but the body.
 *
 * **RED DEMONSTRATIONS (2026-09-25):** "keeps the endpoint out of the URL" went
 * red with `getPushState` rewritten as
 * `request(\`/push/state?endpoint=${encodeURIComponent(endpoint)}\`)`;
 * "sends the browser's subscription as it is" went red with the body built as
 * `JSON.stringify({ endpoint: subscription.endpoint })`.
 */

function stubFetch(body: unknown) {
  const fetchMock = vi.fn().mockImplementation(
    async () =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const ENDPOINT = fixture.subscription.endpoint;

describe("the push API client", () => {
  it("reads the key with a plain GET, credentials included", async () => {
    const fetchMock = stubFetch(fixture.key_set);
    await expect(getPushKey()).resolves.toEqual(fixture.key_set);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/push/key");
    expect(init.credentials).toBe("include");
    expect(init.method ?? "GET").toBe("GET");
  });

  it("sends the browser's subscription as it is", async () => {
    const fetchMock = stubFetch(fixture.on);
    await expect(subscribePush(fixture.subscription)).resolves.toEqual({ on: true });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/push/subscribe");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual(fixture.subscription);
  });

  it("keeps the endpoint out of the URL on every call", async () => {
    const fetchMock = stubFetch(fixture.off);
    await unsubscribePush(ENDPOINT);
    await getPushState(ENDPOINT);
    await subscribePush(fixture.subscription);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "http://api.test/push/unsubscribe",
      "http://api.test/push/state",
      "http://api.test/push/subscribe",
    ]);
    for (const [url, init] of fetchMock.mock.calls) {
      expect(url).not.toContain("example.invalid");
      expect(url).not.toContain(encodeURIComponent(ENDPOINT));
      expect(init.method).toBe("POST");
      // Positive control: it is in the body.
      expect(JSON.parse(init.body).endpoint).toBe(ENDPOINT);
    }
  });
});
