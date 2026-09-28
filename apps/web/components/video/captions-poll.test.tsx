import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MeaningsMap, VideoBlockPayload } from "@/lib/api";

vi.mock("next/navigation", () => ({ usePathname: () => "/watch" }));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    reportVideoProgress: vi.fn(),
    saveWord: vi.fn(),
    lookupWord: vi.fn(),
    videoMeanings: vi.fn(),
    defineWord: vi.fn(),
  };
});

const api = await import("@/lib/api");
const { VideoPlayer, CAPTIONS_POLL_MS, forgetCaptionsTip } = await import("./player");

/**
 * **W32f (B1) — YouTube's captions turned on MID-PLAY.** W32e switched them
 * off once, at `onReady`; the operator then turned CC on during playback
 * (desktop Chrome, 2026-09-28): *"Subtitles/CC turned on"*, both tracks showing,
 * no hint. The IFrame API has no event for a caption toggle, so **while
 * playing, the player asks every 2 s** (`getOption('captions','track')`,
 * undocumented, guarded): a track → the hint; cleared → no hint. **Where the
 * player cannot say** (no `getOption`, or it has never answered with a track
 * object), **a one-time tip the first time the learner enters full screen**,
 * remembered in memory for the session only — no browser storage (CLAUDE.md §5).
 *
 * The fake's `getOption` is a spy, so *"the polling stopped"* is a count that
 * does not grow.
 *
 * **RED BEFORE THE CODE (2026-09-28, on `ca55e40`).**
 */

const MAP: MeaningsMap = {
  l1: "fa", entries: {}, forms: {}, here: {}, names: [], saved: {}, images: {},
};

function payload(): VideoBlockPayload {
  return {
    video_id: 11, youtube_id: "y_525lzqbg0", title: "A probe video", duration_s: 60,
    accent: "british", track: "life", resume_position_s: 0, completed: false,
    transcript_available: true, transcript: "hey how are you",
    lines: [{ start: 0, end: 3.5, text: "hey how are you" }],
    lines_timed: true, transcript_lang: "en", unknown_lemmas: [], coverage_band: "in",
  };
}

type Events = {
  onReady?: (e: unknown) => void;
  onApiChange?: (e: unknown) => void;
  onStateChange?: (e: { data: number }) => void;
};

/** A readied player whose captions `track` the test sets. `getOption` absent
 * when `module` is false; returning `undefined` when `answers` is false. */
function fakePlayer({ module = true, answers = true } = {}) {
  const made: {
    track: unknown;
    getOption?: ReturnType<typeof vi.fn>;
    unloadModule?: ReturnType<typeof vi.fn>;
    events: Events;
    ready: () => void;
    state: (data: number) => void;
  }[] = [];
  class FakePlayer {
    track: unknown = {};
    events: Events;
    getOption?: ReturnType<typeof vi.fn>;
    unloadModule?: ReturnType<typeof vi.fn>;
    constructor(_el: HTMLElement, options: { events: Events }) {
      this.events = options.events;
      made.push(this as never);
      last = this as never;
    }
    getCurrentTime = vi.fn(() => 0);
    setPlaybackRate = vi.fn();
    pauseVideo = vi.fn();
    playVideo = vi.fn();
    seekTo = vi.fn();
    getPlayerState = vi.fn(() => 2);
    destroy = vi.fn();
    ready() {
      if (module) {
        this.unloadModule = vi.fn((name: string) => {
          if (name === "captions") this.track = answers ? {} : undefined;
        });
        this.getOption = vi.fn((m: string, k: string) =>
          m === "captions" && k === "track" && answers ? this.track : undefined,
        );
      }
      act(() => this.events.onReady?.({ target: this }));
    }
    state(data: number) {
      act(() => this.events.onStateChange?.({ data }));
    }
  }
  (window as unknown as { YT: unknown }).YT = { Player: FakePlayer };
  return made;
}

type Made = ReturnType<typeof fakePlayer>[number];
/** The player the component made last — each test reads it after `render`. */
let last: Made | null = null;
const fakePlayerRef = (): Made => last!;

const PLAYING = 1;
const PAUSED = 2;

function desktop() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("hover: hover"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

function tick(times = 1) {
  for (let i = 0; i < times; i += 1) act(() => vi.advanceTimersByTime(CAPTIONS_POLL_MS));
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout", "Date"] });
  desktop();
  forgetCaptionsTip();
  vi.mocked(api.reportVideoProgress).mockReset();
  vi.mocked(api.reportVideoProgress).mockResolvedValue({
    video_id: 11, youtube_id: "y_525lzqbg0", title: null, duration_s: 60,
    resume_position_s: 0, completed: false,
  });
  vi.mocked(api.videoMeanings).mockReset();
  vi.mocked(api.videoMeanings).mockResolvedValue(MAP);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  (window as unknown as { YT?: unknown }).YT = undefined;
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  delete document.documentElement.dataset.videoFocus;
});

const hint = () => screen.queryByTestId("yt-captions-hint");
const tip = () => screen.queryByTestId("yt-captions-tip");

describe("B1 — CC turned on during playback: the page notices within two seconds", () => {
  it("polls every 2 s", () => {
    expect(CAPTIONS_POLL_MS).toBe(2000);
  });

  it("a track appears mid-play → the hint; the track clears → no hint", () => {
    fakePlayer();
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const made = fakePlayerRef();
    made.ready();
    made.state(PLAYING);
    tick();
    expect(hint()).toBeNull();
    made.track = { languageCode: "en" };
    tick();
    expect(hint()).toHaveTextContent(
      "YouTube subtitles are on. Tap CC on the video to turn them off — ours are below.",
    );
    made.track = {};
    tick();
    expect(hint()).toBeNull();
  });

  it("does not ask while paused, and asks again when playing resumes", () => {
    fakePlayer();
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const made = fakePlayerRef();
    made.ready();
    made.state(PLAYING);
    tick();
    made.state(PAUSED);
    const asked = made.getOption!.mock.calls.length;
    made.track = { languageCode: "en" };
    tick(3);
    expect(made.getOption!.mock.calls.length).toBe(asked);
    expect(hint()).toBeNull();
    made.state(PLAYING);
    tick();
    expect(hint()).not.toBeNull();
  });

  it("does not ask while the page is hidden", () => {
    fakePlayer();
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const made = fakePlayerRef();
    made.ready();
    made.state(PLAYING);
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    const asked = made.getOption!.mock.calls.length;
    tick(3);
    expect(made.getOption!.mock.calls.length).toBe(asked);
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    tick();
    expect(made.getOption!.mock.calls.length).toBeGreaterThan(asked);
  });

  it("stops asking when the player is unmounted", () => {
    fakePlayer();
    const { unmount } = render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const made = fakePlayerRef();
    made.ready();
    made.state(PLAYING);
    tick();
    unmount();
    const asked = made.getOption!.mock.calls.length;
    tick(3);
    expect(made.getOption!.mock.calls.length).toBe(asked);
  });

  it("a player that can say shows no full-screen tip", async () => {
    fakePlayer();
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const made = fakePlayerRef();
    made.ready();
    await clickFocus();
    expect(tip()).toBeNull();
  });
});

describe("B1 — where the player cannot say: a one-time tip on the first full screen", () => {
  it("getOption absent: the tip on the first full screen, in the operator's words, dismissible", async () => {
    fakePlayer({ module: false });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    fakePlayerRef().ready();
    expect(tip()).toBeNull();
    await clickFocus();
    expect(tip()).toHaveTextContent("Seeing two subtitles? Turn off CC on the video.");
    await clickDismissTip();
    expect(tip()).toBeNull();
  });

  it("getOption that never answers with a track object counts as absent", async () => {
    fakePlayer({ answers: false });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const made = fakePlayerRef();
    made.ready();
    made.state(PLAYING);
    tick(2);
    await clickFocus();
    expect(tip()).not.toBeNull();
  });

  it("only the first full screen of the session — not the second, not after a remount", async () => {
    fakePlayer({ module: false });
    const { unmount } = render(<VideoPlayer payload={payload()} l1Language="fa" />);
    fakePlayerRef().ready();
    await clickFocus();
    expect(tip()).not.toBeNull();
    await clickDismissTip();
    await clickExit();
    await clickFocus();
    expect(tip()).toBeNull();
    unmount();
    fakePlayer({ module: false });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    fakePlayerRef().ready();
    await clickFocus();
    expect(tip()).toBeNull();
  });

  it("is kept in memory, never in browser storage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    fakePlayer({ module: false });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    fakePlayerRef().ready();
    await clickFocus();
    await clickDismissTip();
    expect(setItem).not.toHaveBeenCalled();
    setItem.mockRestore();
  });
});

// ── helpers ────────────────────────────────────────────────────────────────

// `fireEvent`, not `userEvent`: this file runs on fake timers, and a click
// needs none.
async function clickFocus() {
  act(() => {
    fireEvent.click(screen.getByTestId("focus-enter"));
  });
}
async function clickExit() {
  act(() => {
    fireEvent.click(screen.getByTestId("focus-exit"));
  });
}
async function clickDismissTip() {
  act(() => {
    fireEvent.click(screen.getByTestId("yt-captions-tip-dismiss"));
  });
}
