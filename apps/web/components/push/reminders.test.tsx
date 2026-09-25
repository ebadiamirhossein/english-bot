import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { REMINDERS } from "@/components/session/copy";

import fixture from "./push.fixture.json";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getPushKey: vi.fn(),
    getPushState: vi.fn(),
    subscribePush: vi.fn(),
    unsubscribePush: vi.fn(),
  };
});

const api = await import("@/lib/api");
const { Reminders } = await import("./reminders");

/**
 * W20's client half: the reminder control in the settings menu, drawn from
 * `push.fixture.json` — bodies built by `scripts/export_push_fixture.py` through
 * the real `GET /push/key` route and the `PushStateOut` / `PushSubscriptionIn`
 * schemas (#190). The browser half (`serviceWorker`, `PushManager`,
 * `Notification`) is a stub: jsdom has none of it, and **no test here can show a
 * real browser grants permission or delivers a push** — that is the operator's
 * phone check.
 *
 * **Every "draws nothing" assertion is paired with a positive control** (#345):
 * an empty container passes whether the rule holds or the component is broken.
 *
 * **RED DEMONSTRATIONS (2026-09-25), each by one edit to `reminders.tsx`, run,
 * and restored:**
 * - "draws nothing when the server has no key" — `if (!key) return hidden`
 *   deleted: the switch drew for a `null` key.
 * - "draws nothing where the browser has no push, off iOS" — the
 *   `!pushSupported()` line deleted: the dead switch drew. **This one stayed
 *   green on its first run**, because the stub then left `Notification`
 *   undefined too, so the mutated component threw and drew nothing for the
 *   wrong reason. The stub now defines `Notification` without `PushManager`,
 *   and the component catches an unexpected throw as "hidden" explicitly.
 * - "on iOS in a Safari tab, says to add the app to the Home Screen" —
 *   `needsHomeScreen() ? "install" : "hidden"` changed to `"hidden"`.
 * - "says reminders are blocked, and draws no switch" — the `permission ===
 *   "denied"` line deleted: the switch drew.
 * - "reads this browser's state from the server" — `on ? "on" : "off"` in
 *   `firstPhase` changed to `"off"`.
 * - "a subscription the server has forgotten is off" — the same line changed to
 *   `"on"`.
 * - "asks permission inside the tap" — `await Promise.resolve()` put ahead of
 *   `requestPermission` in `turnOn`: the request was not made by the time the
 *   click handler returned.
 * - "turning it on subscribes with the server's key and tells the server" —
 *   `applicationServerKey: key` changed to `applicationServerKey: undefined`.
 * - "is disabled and shows the dots while it works" — `disabled={busy}` removed.
 * - "turning it off tells the server first" — the `unsubscribePush(...)` call
 *   replaced by `const on = false` (the switch still flipped; the server was
 *   never told).
 * - "a refused prompt shows the blocked line" — `return "blocked"` changed to
 *   `return "closed"`.
 * - "on iOS opened from the Home Screen without push, draws nothing" —
 *   `needsHomeScreen` made to return `true` whatever `standalone` says.
 * - "with no subscription here, is off and asks the server nothing more" — the
 *   no-subscription branch made to call `getPushState` anyway.
 * - "a closed prompt changes nothing" — `setNote("closed")` removed.
 * - "trouble on the way says so and changes nothing" — `.catch(() =>
 *   setNote("trouble"))` changed to `.catch(() => undefined)`.
 * - "never writes the endpoint to the console" — `console.info(subscription
 *   .endpoint)` added to `firstPhase`.
 * - "carries no numeral and no guilt" — `about` given " Up to 3 a day." in
 *   `copy.ts`.
 */

const KEY = fixture.key_set.public_key as string;
const ENDPOINT = fixture.subscription.endpoint;

type Stub = {
  permission?: NotificationPermission;
  answer?: NotificationPermission;
  subscribed?: boolean;
  push?: boolean;
  userAgent?: string;
  standalone?: boolean;
};

const IPHONE =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1";

const owned: [object, string][] = [];

function define(target: object, name: string, value: unknown) {
  Object.defineProperty(target, name, { configurable: true, writable: true, value });
  owned.push([target, name]);
}

function subscription() {
  return {
    endpoint: ENDPOINT,
    toJSON: () => fixture.subscription,
    unsubscribe: vi.fn().mockResolvedValue(true),
  };
}

/** The three browser APIs, stubbed onto jsdom's `window` and `navigator`. */
function browser({
  permission = "default",
  answer = "granted",
  subscribed = false,
  push = true,
  userAgent,
  standalone = false,
}: Stub = {}) {
  const existing = subscribed ? subscription() : null;
  const fresh = subscription();
  const pushManager = {
    getSubscription: vi.fn().mockResolvedValue(existing),
    subscribe: vi.fn().mockResolvedValue(fresh),
  };
  const requestPermission = vi.fn().mockResolvedValue(answer);
  define(navigator, "serviceWorker", { ready: Promise.resolve({ pushManager }) });
  // `Notification` is defined either way: a browser with notifications and no
  // push (a desktop engine without `PushManager`) is the case the support check
  // exists for — without it the component would go on and draw a dead switch.
  define(window, "Notification", { permission, requestPermission });
  if (push) define(window, "PushManager", function PushManager() {});
  if (userAgent) define(navigator, "userAgent", userAgent);
  define(navigator, "standalone", standalone);
  return { pushManager, requestPermission, existing, fresh };
}

afterEach(() => {
  for (const [target, name] of owned.splice(0)) {
    delete (target as Record<string, unknown>)[name];
  }
});

function key(body: unknown = fixture.key_set) {
  vi.mocked(api.getPushKey).mockResolvedValue(body as Awaited<ReturnType<typeof api.getPushKey>>);
}

async function drawn(phase: string) {
  await waitFor(() => expect(screen.getByTestId("reminders").dataset.phase).toBe(phase));
}

/** Let every pending promise in the component settle. */
async function settle() {
  await act(async () => {
    for (let i = 0; i < 10; i += 1) await Promise.resolve();
  });
}

const toggle = () => screen.getByRole("menuitemcheckbox", { name: new RegExp(`^${REMINDERS.toggle}`) });

describe("the reminder control", () => {
  it("draws nothing when the server has no key", async () => {
    browser();
    // Positive control: the same browser with a key draws the switch.
    key();
    const first = render(<Reminders />);
    await drawn("off");
    first.unmount();

    key(fixture.key_unset);
    const { container } = render(<Reminders />);
    await settle();
    expect(api.getPushKey).toHaveBeenCalledTimes(2);
    expect(container).toBeEmptyDOMElement();
  });

  it("draws nothing where the browser has no push, off iOS", async () => {
    key();
    browser({ push: false });
    const { container } = render(<Reminders />);
    await settle();
    expect(api.getPushKey).toHaveBeenCalled();
    expect(container).toBeEmptyDOMElement();
  });

  it("on iOS in a Safari tab, says to add the app to the Home Screen", async () => {
    key();
    browser({ push: false, userAgent: IPHONE });
    render(<Reminders />);
    await drawn("install");
    expect(screen.getByTestId("reminders-install")).toHaveTextContent(REMINDERS.install);
    expect(screen.queryByRole("menuitemcheckbox")).toBeNull();
  });

  it("on iOS opened from the Home Screen without push, draws nothing", async () => {
    key();
    browser({ push: false, userAgent: IPHONE, standalone: true });
    const { container } = render(<Reminders />);
    await settle();
    expect(container).toBeEmptyDOMElement();
  });

  it("says reminders are blocked, and draws no switch", async () => {
    key();
    browser({ permission: "denied" });
    render(<Reminders />);
    await drawn("blocked");
    expect(screen.getByTestId("reminders-blocked")).toHaveTextContent(REMINDERS.blocked);
    expect(screen.queryByRole("menuitemcheckbox")).toBeNull();
  });

  it("with no subscription here, is off and asks the server nothing more", async () => {
    key();
    browser();
    render(<Reminders />);
    await drawn("off");
    expect(toggle()).toHaveAttribute("aria-checked", "false");
    expect(toggle()).toBeEnabled();
    expect(screen.getByTestId("reminders-about")).toHaveTextContent(REMINDERS.about);
    expect(api.getPushState).not.toHaveBeenCalled();
  });

  it("reads this browser's state from the server", async () => {
    key();
    browser({ permission: "granted", subscribed: true });
    vi.mocked(api.getPushState).mockResolvedValue(fixture.on);
    render(<Reminders />);
    await drawn("on");
    expect(toggle()).toHaveAttribute("aria-checked", "true");
    expect(api.getPushState).toHaveBeenCalledWith(ENDPOINT);
  });

  it("a subscription the server has forgotten is off", async () => {
    key();
    browser({ permission: "granted", subscribed: true });
    vi.mocked(api.getPushState).mockResolvedValue(fixture.off);
    render(<Reminders />);
    await drawn("off");
    expect(toggle()).toHaveAttribute("aria-checked", "false");
  });

  it("asks permission inside the tap, before anything is awaited", async () => {
    key();
    const b = browser();
    vi.mocked(api.subscribePush).mockResolvedValue(fixture.on);
    render(<Reminders />);
    await drawn("off");
    fireEvent.click(toggle());
    // Synchronously: iOS only honours a request made inside the gesture.
    expect(b.requestPermission).toHaveBeenCalledTimes(1);
    await drawn("on");
  });

  it("turning it on subscribes with the server's key and tells the server", async () => {
    key();
    const b = browser();
    vi.mocked(api.subscribePush).mockResolvedValue(fixture.on);
    render(<Reminders />);
    await drawn("off");
    fireEvent.click(toggle());
    await drawn("on");
    expect(b.pushManager.subscribe).toHaveBeenCalledWith({
      userVisibleOnly: true,
      applicationServerKey: KEY,
    });
    expect(api.subscribePush).toHaveBeenCalledWith(fixture.subscription);
    expect(toggle()).toHaveAttribute("aria-checked", "true");
  });

  it("is disabled and shows the dots while it works", async () => {
    key();
    browser();
    let release!: () => void;
    vi.mocked(api.subscribePush).mockReturnValue(
      new Promise((resolve) => {
        release = () => resolve(fixture.on);
      }),
    );
    render(<Reminders />);
    await drawn("off");
    fireEvent.click(toggle());
    await waitFor(() => expect(screen.getByTestId("reminders-working")).toBeInTheDocument());
    expect(toggle()).toBeDisabled();
    expect(toggle()).toHaveAttribute("aria-busy", "true");
    fireEvent.click(toggle());
    release();
    await drawn("on");
    expect(api.subscribePush).toHaveBeenCalledTimes(1);
    expect(toggle()).toBeEnabled();
    expect(screen.queryByTestId("reminders-working")).toBeNull();
  });

  it("turning it off tells the server first, then the browser", async () => {
    key();
    const b = browser({ permission: "granted", subscribed: true });
    vi.mocked(api.getPushState).mockResolvedValue(fixture.on);
    vi.mocked(api.unsubscribePush).mockResolvedValue(fixture.off);
    render(<Reminders />);
    await drawn("on");
    fireEvent.click(toggle());
    await drawn("off");
    expect(api.unsubscribePush).toHaveBeenCalledWith(ENDPOINT);
    expect(b.existing!.unsubscribe).toHaveBeenCalled();
    expect(vi.mocked(api.unsubscribePush).mock.invocationCallOrder[0]).toBeLessThan(
      b.existing!.unsubscribe.mock.invocationCallOrder[0],
    );
    expect(b.requestPermission).not.toHaveBeenCalled();
  });

  it("a refused prompt shows the blocked line", async () => {
    key();
    browser({ answer: "denied" });
    render(<Reminders />);
    await drawn("off");
    fireEvent.click(toggle());
    await drawn("blocked");
    expect(api.subscribePush).not.toHaveBeenCalled();
  });

  it("a closed prompt changes nothing, and says so calmly", async () => {
    key();
    browser({ answer: "default" });
    render(<Reminders />);
    await drawn("off");
    fireEvent.click(toggle());
    await waitFor(() =>
      expect(screen.getByTestId("reminders-closed")).toHaveTextContent(REMINDERS.closed),
    );
    expect(toggle()).toHaveAttribute("aria-checked", "false");
    expect(api.subscribePush).not.toHaveBeenCalled();
  });

  it("trouble on the way says so and changes nothing", async () => {
    key();
    browser();
    vi.mocked(api.subscribePush).mockRejectedValue(new api.ApiError("/push/subscribe returned 500", 500));
    render(<Reminders />);
    await drawn("off");
    fireEvent.click(toggle());
    await waitFor(() =>
      expect(screen.getByTestId("reminders-trouble")).toHaveTextContent(REMINDERS.trouble),
    );
    expect(toggle()).toHaveAttribute("aria-checked", "false");
    expect(toggle()).toBeEnabled();
  });

  it("never writes the endpoint to the console", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((m) =>
      vi.spyOn(console, m).mockImplementation(() => undefined),
    );
    key();
    browser({ permission: "granted", subscribed: true });
    vi.mocked(api.getPushState).mockResolvedValue(fixture.on);
    vi.mocked(api.unsubscribePush).mockResolvedValue(fixture.off);
    render(<Reminders />);
    await drawn("on");
    fireEvent.click(toggle());
    await drawn("off");
    // Positive control: the endpoint really was in hand.
    expect(api.unsubscribePush).toHaveBeenCalledWith(ENDPOINT);
    for (const spy of spies) {
      for (const call of spy.mock.calls) {
        expect(JSON.stringify(call)).not.toContain("example.invalid");
      }
    }
  });

  it("carries no numeral and no guilt in any of its words", () => {
    const words = Object.values(REMINDERS);
    // Positive control: the block is what the component draws.
    expect(words).toContain(REMINDERS.about);
    expect(words.length).toBeGreaterThan(5);
    const guilt =
      /\bmissed\b|\bfailed?\b|\bfailure\b|\bbroke\b|should have|\bwrong\b|\bincorrect\b|try harder|you lost|behind|overdue|don['’]t forget|streak|\blate\b(?! at night)|lose|nag/i;
    for (const text of words) {
      expect(text, text).not.toMatch(/[0-9]/);
      expect(text, text).not.toMatch(guilt);
    }
  });
});
