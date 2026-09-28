import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
const { VideoPlayer } = await import("./player");
const { WordSheet } = await import("./word-sheet");

/**
 * **W32e — the operator's first real use of `/watch` (2026-09-28).** jsdom has
 * no layout, so whether Save is ON the screen, and whether the nav is drawn
 * over anything, is Playwright's (`e2e/watch-fixes.spec.ts`). This file holds
 * the rules: the listener every Safari has, the nav flag in Focus, the two
 * full-screen buttons, YouTube's captions (guarded, undocumented), the
 * sheet's parts, and the saved copy.
 *
 * **RED BEFORE THE CODE (2026-09-28, on `f8ce946`).**
 */

const MAP: MeaningsMap = {
  l1: "fa",
  entries: {
    model: {
      k: "w", r: "neutral",
      s: [
        ["noun", "a small copy of something bigger", "ماکت"],
        ["noun", "a person whose job is to wear clothes for photos", "مدل"],
      ],
    },
  },
  forms: {}, here: {}, names: [], saved: {}, images: {},
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

beforeEach(() => {
  vi.mocked(api.reportVideoProgress).mockReset();
  vi.mocked(api.reportVideoProgress).mockResolvedValue({
    video_id: 11, youtube_id: "y_525lzqbg0", title: null, duration_s: 60,
    resume_position_s: 0, completed: false,
  });
  vi.mocked(api.videoMeanings).mockReset();
  vi.mocked(api.videoMeanings).mockResolvedValue(MAP);
  vi.mocked(api.saveWord).mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  (window as unknown as { YT?: unknown }).YT = undefined;
  delete document.documentElement.dataset.videoFocus;
});

const root = () => screen.getByTestId("video-player");

/**
 * **A `MediaQueryList` as Safari before 14 has it: `addListener` and
 * `removeListener`, and NO `addEventListener`** — it is not an `EventTarget`
 * there. `modern: true` gives the `EventTarget` half instead, as today's.
 */
function webkitMedia(initial: { landscape: boolean; coarse: boolean }, modern = false) {
  const state = { ...initial };
  const listeners = new Set<() => void>();
  const removed: unknown[] = [];
  const matches = (query: string) => {
    if (query.includes("orientation: landscape")) return state.landscape && state.coarse;
    if (query.includes("pointer: coarse")) return state.coarse;
    if (query.includes("hover: hover")) return !state.coarse;
    return false;
  };
  vi.stubGlobal("matchMedia", (query: string) => {
    const list: Record<string, unknown> = {
      get matches() {
        return matches(query);
      },
      media: query,
    };
    if (modern) {
      list.addEventListener = (type: string, fn: () => void) => type === "change" && listeners.add(fn);
      list.removeEventListener = (type: string, fn: () => void) => {
        removed.push(fn);
        listeners.delete(fn);
      };
    } else {
      list.addListener = (fn: () => void) => listeners.add(fn);
      list.removeListener = (fn: () => void) => {
        removed.push(fn);
        listeners.delete(fn);
      };
    }
    return list;
  });
  (window as unknown as { matchMedia: unknown }).matchMedia = globalThis.matchMedia;
  return {
    turn(landscape: boolean) {
      state.landscape = landscape;
      act(() => listeners.forEach((fn) => fn()));
    },
    listening: () => listeners.size,
    removed,
  };
}

describe("B2 — turning an iPhone whose MediaQueryList has only addListener", () => {
  it("sideways after load enters Focus, and upright exits", async () => {
    const phone = webkitMedia({ landscape: false, coarse: true });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(root().dataset.focus).toBe("off");
    expect(phone.listening()).toBeGreaterThan(0);
    phone.turn(true);
    await waitFor(() => expect(root().dataset.focus).not.toBe("off"));
    phone.turn(false);
    await waitFor(() => expect(root().dataset.focus).toBe("off"));
  });

  it("removes its listener on unmount, through removeListener", () => {
    const phone = webkitMedia({ landscape: false, coarse: true });
    const { unmount } = render(<VideoPlayer payload={payload()} l1Language="fa" />);
    unmount();
    expect(phone.removed.length).toBeGreaterThan(0);
    expect(phone.listening()).toBe(0);
  });

  it("still uses the change event where the list is an EventTarget", async () => {
    const phone = webkitMedia({ landscape: false, coarse: true }, true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    phone.turn(true);
    await waitFor(() => expect(root().dataset.focus).not.toBe("off"));
  });
});

describe("B2 — the bottom nav steps aside for Focus", () => {
  it("marks <html> while in Focus, and clears it on exit and on unmount", async () => {
    webkitMedia({ landscape: false, coarse: true }, true);
    const { unmount } = render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(document.documentElement.dataset.videoFocus).toBeUndefined();
    await userEvent.click(screen.getByTestId("focus-enter"));
    expect(document.documentElement.dataset.videoFocus).toBe("fixed");
    await userEvent.click(screen.getByTestId("focus-exit"));
    expect(document.documentElement.dataset.videoFocus).toBeUndefined();
    await userEvent.click(screen.getByTestId("focus-enter"));
    unmount();
    expect(document.documentElement.dataset.videoFocus).toBeUndefined();
  });

  it("the nav carries the marker the stylesheet hides", async () => {
    const { BottomNav } = await import("@/components/bottom-nav");
    render(<BottomNav />);
    expect(screen.getByRole("navigation", { name: "Main" })).toHaveAttribute("data-bottom-nav");
  });
});

describe("B1 — full screen, where people look for it", () => {
  it("the row's button reads Full screen with an icon; its exit reads Exit full screen", async () => {
    webkitMedia({ landscape: false, coarse: false }, true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const row = screen.getByTestId("focus-enter");
    expect(row).toHaveTextContent(/^Full screen$/);
    expect(row.querySelector("svg")).not.toBeNull();
    await userEvent.click(row);
    const exit = screen.getByTestId("focus-exit");
    expect(exit).toHaveTextContent(/^Exit full screen$/);
    expect(exit.querySelector("svg")).not.toBeNull();
  });

  it("a second button on the video's corner, in our layer above the iframe, enters Focus", async () => {
    webkitMedia({ landscape: false, coarse: true }, true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const corner = screen.getByTestId("focus-corner");
    expect(corner).toHaveAccessibleName("Full screen");
    expect(screen.getByTestId("video-box").contains(corner)).toBe(true);
    expect(screen.getByTestId("player-mount").contains(corner)).toBe(false);
    expect(corner.className).toMatch(/absolute/);
    expect(corner.className).toMatch(/bottom-/);
    expect(corner.className).toMatch(/right-/);
    await userEvent.click(corner);
    expect(root().dataset.focus).not.toBe("off");
    // In Focus the picture stays clear; the exit is the row's.
    expect(screen.queryByTestId("focus-corner")).toBeNull();
  });
});

/**
 * **A player with YouTube's undocumented captions module**, whose methods
 * arrive at `onReady` like the rest (W31a). `module`: which of the three
 * methods it has. `track`: what `getOption('captions','track')` returns;
 * `sticks`: unloading leaves the track on.
 */
type Fake = {
  options: { events?: { onReady?: (e: unknown) => void; onApiChange?: (e: unknown) => void } };
  unloadModule?: ReturnType<typeof vi.fn>;
  setOption?: ReturnType<typeof vi.fn>;
  getOption?: ReturnType<typeof vi.fn>;
  track: unknown;
  ready: () => void;
  apiChange: () => void;
};

function fakePlayer({
  module = ["unloadModule", "getOption"] as ("unloadModule" | "setOption" | "getOption")[],
  track = { languageCode: "en" } as unknown,
  sticks = false,
} = {}): Fake[] {
  const made: Fake[] = [];
  class FakePlayer {
    options: Fake["options"];
    track = track;
    unloadModule?: ReturnType<typeof vi.fn>;
    setOption?: ReturnType<typeof vi.fn>;
    getOption?: ReturnType<typeof vi.fn>;
    constructor(_el: HTMLElement, options: Fake["options"]) {
      this.options = options;
      made.push(this as unknown as Fake);
    }
    getCurrentTime = vi.fn(() => 0);
    setPlaybackRate = vi.fn();
    pauseVideo = vi.fn();
    playVideo = vi.fn();
    seekTo = vi.fn();
    getPlayerState = vi.fn(() => 2);
    destroy = vi.fn();
    ready() {
      if (module.includes("unloadModule")) {
        this.unloadModule = vi.fn((name: string) => {
          if (name === "captions" && !sticks) this.track = {};
        });
      }
      if (module.includes("setOption")) {
        this.setOption = vi.fn((m: string, k: string, v: unknown) => {
          if (m === "captions" && k === "track" && !sticks) this.track = v;
        });
      }
      if (module.includes("getOption")) {
        this.getOption = vi.fn((m: string, k: string) => (m === "captions" && k === "track" ? this.track : undefined));
      }
      act(() => this.options.events?.onReady?.({ target: this }));
    }
    apiChange() {
      act(() => this.options.events?.onApiChange?.({ target: this }));
    }
  }
  (window as unknown as { YT: unknown }).YT = { Player: FakePlayer };
  return made;
}

describe("B3 — YouTube's own captions (the module is undocumented; every call guarded)", () => {
  beforeEach(() => webkitMedia({ landscape: false, coarse: true }, true));

  it("a saved caption preference: unloaded at ready, and no hint", () => {
    const made = fakePlayer();
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    made[0].ready();
    expect(made[0].unloadModule).toHaveBeenCalledWith("captions");
    expect(root().dataset.ytCaptions).toBe("off");
    expect(screen.queryByTestId("yt-captions-hint")).toBeNull();
  });

  it("with only setOption, sets an empty track instead", () => {
    const made = fakePlayer({ module: ["setOption", "getOption"] });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    made[0].ready();
    expect(made[0].setOption).toHaveBeenCalledWith("captions", "track", {});
    expect(root().dataset.ytCaptions).toBe("off");
  });

  it("a player with none of the three: nothing throws, nothing is guessed, no hint", () => {
    const made = fakePlayer({ module: [] });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(() => made[0].ready()).not.toThrow();
    expect(() => made[0].apiChange()).not.toThrow();
    expect(root().dataset.ytCaptions).toBe("unknown");
    expect(screen.queryByTestId("yt-captions-hint")).toBeNull();
  });

  it("unloading with no way to see the track: tried at ready and at the first module change, never shown a hint", () => {
    const made = fakePlayer({ module: ["unloadModule"] });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    made[0].ready();
    made[0].apiChange();
    made[0].apiChange();
    expect(made[0].unloadModule).toHaveBeenCalledTimes(2);
    expect(root().dataset.ytCaptions).toBe("unknown");
    expect(screen.queryByTestId("yt-captions-hint")).toBeNull();
  });

  it("a module that loads after ready (playback starts): unloaded when it appears", () => {
    // No module loaded yet: `getOption` answers nothing.
    const made = fakePlayer({ track: null });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    made[0].ready();
    expect(made[0].unloadModule).not.toHaveBeenCalled();
    made[0].track = { languageCode: "en" };
    made[0].apiChange();
    expect(made[0].unloadModule).toHaveBeenCalledTimes(1);
    expect(root().dataset.ytCaptions).toBe("off");
  });

  it("captions that will not go: the hint, in the operator's words, dismissible", async () => {
    const made = fakePlayer({ sticks: true });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    made[0].ready();
    const hint = screen.getByTestId("yt-captions-hint");
    expect(hint).toHaveTextContent(
      "YouTube subtitles are on. Tap CC on the video to turn them off — ours are below.",
    );
    await userEvent.click(within(hint).getByTestId("yt-captions-hint-dismiss"));
    expect(screen.queryByTestId("yt-captions-hint")).toBeNull();
  });

  it("switched off once: a learner who turns YouTube's CC back on keeps it", () => {
    const made = fakePlayer();
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    made[0].ready();
    made[0].track = { languageCode: "en" };
    made[0].apiChange();
    expect(made[0].unloadModule).toHaveBeenCalledTimes(1);
    expect(root().dataset.ytCaptions).toBe("on");
  });

  it("no hint in Focus, where ours are on the picture rather than below", async () => {
    const made = fakePlayer({ sticks: true });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    made[0].ready();
    expect(screen.getByTestId("yt-captions-hint")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("focus-enter"));
    expect(screen.queryByTestId("yt-captions-hint")).toBeNull();
  });
});

describe("B2 and B4 — the sheet: Save in a footer that never scrolls away; the saved copy", () => {
  function openSheet() {
    render(
      <WordSheet
        videoId={11}
        target={{ word: "model", line: 0 }}
        onClose={() => {}}
        map={MAP}
        lineText="it's a model of one."
      />,
    );
  }

  it("the body scrolls; Save is outside it, in the footer; the sheet is held to the viewport", () => {
    openSheet();
    const sheet = screen.getByTestId("word-sheet");
    const body = screen.getByTestId("word-sheet-body");
    const footer = screen.getByTestId("word-sheet-footer");
    const save = screen.getByTestId("word-sheet-save");
    expect(body.className).toMatch(/overflow-y-auto/);
    expect(body.className).toMatch(/min-h-0/);
    expect(body.contains(save)).toBe(false);
    expect(footer.contains(save)).toBe(true);
    expect(footer.className).toMatch(/shrink-0/);
    expect(footer.className).toMatch(/safe-area-inset-bottom/);
    expect(sheet.className).toMatch(/flex-col/);
    expect(sheet.className).toMatch(/max-h-\[75dvh\]/);
    expect(sheet.className).toMatch(/100dvh/);
    expect(sheet.className).toMatch(/safe-area-inset-left/);
    expect(sheet.className).toMatch(/safe-area-inset-right/);
    expect(within(body).getAllByTestId("word-sheet-sense")).toHaveLength(2);
  });

  it("after Save: where the word will be practised, plainly, with no count", async () => {
    vi.mocked(api.saveWord).mockResolvedValue({ state: "saved", card_ids: [1, 2] } as never);
    openSheet();
    await userEvent.click(screen.getByTestId("word-sheet-save"));
    expect(await screen.findByTestId("save-word-result")).toHaveTextContent(
      "Saved. You’ll practise it in Review and in word practice.",
    );
    expect(screen.getByTestId("word-sheet-footer").contains(screen.getByTestId("save-word-result"))).toBe(true);
  });
});
