import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

/**
 * W20 — the service worker's push and tap handlers, run against a stub of the
 * worker scope.
 *
 * jsdom's `self` is the window, so importing `worker/index.ts` here registers
 * its two listeners on it; `registration` and `clients` are stubbed onto the
 * same object and events are dispatched at it. **This proves the handlers'
 * logic, not that a phone shows the notification or that iOS opens the app on a
 * tap** — the Playwright config blocks service workers entirely, and the
 * operator's phone check is the only place a real push is seen.
 *
 * **RED DEMONSTRATIONS (2026-09-25), each one edit to `worker/index.ts`, run,
 * and restored:** "shows the server's title and body" went red with `body:`
 * hardcoded to `""`; "keeps the tap on this origin" went red with `samePath`
 * returning `raw` whenever it starts with `/` (the `//` and `/\` cases then
 * opened another host); "focuses an open window and moves it to the session"
 * went red with the `open.navigate(target)` call removed; "opens the app at the
 * session when no window is open" went red with the final `openWindow` removed;
 * "still shows a notification when the payload is empty or not JSON" went red
 * with the `try`/`catch` around `event.data.json()` removed.
 */

const scope = self as unknown as Record<string, unknown>;

function extendable(type: string, extra: Record<string, unknown>) {
  const pending: Promise<unknown>[] = [];
  const event = Object.assign(new Event(type), extra, {
    waitUntil: (p: Promise<unknown>) => pending.push(p),
  });
  return { event, done: () => Promise.all(pending) };
}

const NOT_JSON = Symbol("not json");

async function push(data: unknown) {
  const showNotification = vi.fn().mockResolvedValue(undefined);
  scope.registration = { showNotification };
  const json = () => {
    if (data === NOT_JSON) throw new SyntaxError("Unexpected token");
    return data;
  };
  const { event, done } = extendable("push", { data: data === undefined ? null : { json } });
  self.dispatchEvent(event);
  await done();
  return showNotification;
}

async function tap(url: unknown, windows: { url: string }[] = []) {
  const clients = windows.map((w) => ({
    url: w.url,
    focus: vi.fn().mockResolvedValue(undefined),
    navigate: vi.fn().mockResolvedValue(undefined),
  }));
  const openWindow = vi.fn().mockResolvedValue(undefined);
  scope.clients = { matchAll: vi.fn().mockResolvedValue(clients), openWindow };
  const close = vi.fn();
  const { event, done } = extendable("notificationclick", {
    notification: { close, data: { url } },
  });
  self.dispatchEvent(event);
  await done();
  return { close, openWindow, clients };
}

const ORIGIN = self.location.origin;

beforeAll(async () => {
  await import("./index");
});

afterEach(() => {
  delete scope.registration;
  delete scope.clients;
});

describe("the service worker", () => {
  it("shows the server's title and body, tagged so a nudge replaces the reminder", async () => {
    const show = await push({ title: "Today’s session", body: "It’s ready whenever you are.", url: "/session" });
    expect(show).toHaveBeenCalledTimes(1);
    const [title, options] = show.mock.calls[0];
    expect(title).toBe("Today’s session");
    expect(options.body).toBe("It’s ready whenever you are.");
    expect(options.data).toEqual({ url: "/session" });
    expect(options.tag).toBe("daily-reminder");
    expect(options.icon).toBe("/icons/icon-192.png");
  });

  it("still shows a notification when the payload is empty or not JSON", async () => {
    // `userVisibleOnly` obliges one; a push that shows nothing is a broken promise.
    const empty = await push(undefined);
    expect(empty).toHaveBeenCalledWith("English", expect.objectContaining({ body: "" }));
    const garbled = await push(NOT_JSON);
    expect(garbled).toHaveBeenCalledWith(
      "English",
      expect.objectContaining({ body: "", data: { url: "/session" } }),
    );
  });

  it("keeps the tap on this origin", async () => {
    for (const hostile of ["https://evil.example/x", "//evil.example/x", "/\\evil.example/x", 42]) {
      const { openWindow } = await tap(hostile);
      expect(openWindow, String(hostile)).toHaveBeenCalledWith(`${ORIGIN}/session`);
    }
    // Positive control: a path of our own is kept, query and all.
    const { openWindow } = await tap("/write?from=push");
    expect(openWindow).toHaveBeenCalledWith(`${ORIGIN}/write?from=push`);
  });

  it("focuses an open window and moves it to the session", async () => {
    const { close, openWindow, clients } = await tap("/session", [{ url: `${ORIGIN}/progress` }]);
    expect(close).toHaveBeenCalled();
    expect(clients[0].focus).toHaveBeenCalled();
    expect(clients[0].navigate).toHaveBeenCalledWith(`${ORIGIN}/session`);
    expect(openWindow).not.toHaveBeenCalled();
  });

  it("opens the app at the session when no window is open", async () => {
    const { close, openWindow } = await tap("/session", [{ url: "https://elsewhere.example/" }]);
    expect(close).toHaveBeenCalled();
    expect(openWindow).toHaveBeenCalledWith(`${ORIGIN}/session`);
  });
});
