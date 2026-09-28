import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MeaningsMap, VideoBlockPayload } from "@/lib/api";

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

/**
 * **W32d — the line ON the video in Focus, and a phone turned sideways enters
 * Focus.** jsdom has no layout, so WHERE the caption is drawn is Playwright's
 * (`e2e/focus-overlay.spec.ts`); this file holds the structure (the caption is
 * inside the video's box, the layer passes the pointer through) and the rules
 * (rotation in and out, a chosen Focus kept, the Android lock).
 *
 * **RED BEFORE THE CODE (2026-09-28):** Focus drew the line under the video,
 * and nothing listened to the orientation.
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

/** A matchMedia whose answers the test sets, and whose `change` it fires. */
function media(initial: { landscape: boolean; coarse: boolean }) {
  const state = { ...initial };
  const listeners = new Set<() => void>();
  const matches = (query: string) => {
    if (query.includes("orientation: landscape")) return state.landscape && state.coarse;
    if (query.includes("pointer: coarse")) return state.coarse;
    if (query.includes("hover: hover")) return !state.coarse;
    return false;
  };
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      return matches(query);
    },
    media: query,
    // Only `change` is an orientation event — a stub that took any name would
    // pass a player listening for the wrong one (found by mutation D3).
    addEventListener: (type: string, fn: () => void) => type === "change" && listeners.add(fn),
    removeEventListener: (type: string, fn: () => void) => type === "change" && listeners.delete(fn),
  }));
  (window as unknown as { matchMedia: unknown }).matchMedia = globalThis.matchMedia;
  return {
    turn(landscape: boolean) {
      state.landscape = landscape;
      act(() => listeners.forEach((fn) => fn()));
    },
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
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const root = () => screen.getByTestId("video-player");

describe("the caption in Focus (W32d on the video; W32f in a strip below it)", () => {
  // **W32f (#487): REPLACED.** This test asserted W32d's caption INSIDE the
  // video's box, in a layer that let the pointer through (*"is drawn inside
  // the video's own box in Focus, and the layer lets the pointer through"*).
  // The operator ruled on 2026-09-28 that the caption moves to a strip BELOW
  // the video — YouTube's Required Minimum Functionality forbids overlays on
  // the embedded player — so the assertion is inverted here, and the strip's
  // own rules are `focus-strip.test.tsx`'s.
  it("is drawn in a strip under the video in Focus, never inside the video's box (W32f)", async () => {
    media({ landscape: false, coarse: false });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await userEvent.click(screen.getByTestId("focus-enter"));
    const box = screen.getByTestId("video-box");
    expect(screen.queryByTestId("caption-layer")).toBeNull();
    expect(box.contains(screen.getByTestId("subtitle-now"))).toBe(false);
    expect(screen.getByTestId("caption-strip").contains(screen.getByTestId("subtitle-now"))).toBe(true);
    expect(screen.getByTestId("subtitle-now")).toHaveTextContent("hey how are you");
    // No previous or next line in the strip — it would take the video's height.
    expect(screen.queryByTestId("subtitle-prev")).toBeNull();
  });

  it("stays under the video, as W31b built it, outside Focus", () => {
    media({ landscape: false, coarse: false });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(screen.queryByTestId("caption-layer")).toBeNull();
    expect(screen.getByTestId("video-box").contains(screen.getByTestId("subtitle-block"))).toBe(false);
    expect(screen.getByTestId("subtitle-prev")).toBeInTheDocument();
  });
});

describe("turning the phone", () => {
  it("sideways enters Focus; upright again exits it", async () => {
    const phone = media({ landscape: false, coarse: true });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(root().dataset.focus).toBe("off");
    phone.turn(true);
    await waitFor(() => expect(root().dataset.focus).not.toBe("off"));
    phone.turn(false);
    await waitFor(() => expect(root().dataset.focus).toBe("off"));
  });

  it("opening the page already sideways starts in Focus", async () => {
    media({ landscape: true, coarse: true });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await waitFor(() => expect(root().dataset.focus).not.toBe("off"));
  });

  it("keeps a Focus the learner chose when the phone turns back upright", async () => {
    const phone = media({ landscape: false, coarse: true });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await userEvent.click(screen.getByTestId("focus-enter"));
    phone.turn(true);
    phone.turn(false);
    expect(root().dataset.focus).not.toBe("off");
  });

  it("does nothing on a desktop, however wide the window", () => {
    const desk = media({ landscape: false, coarse: false });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    desk.turn(true);
    expect(root().dataset.focus).toBe("off");
  });
});

describe("the Android lock (operator ruling Q2)", () => {
  function fullscreenCapable() {
    const lock = vi.fn(() => Promise.resolve());
    const unlock = vi.fn();
    Object.defineProperty(document, "fullscreenEnabled", { configurable: true, value: true });
    Object.defineProperty(window.screen, "orientation", {
      configurable: true,
      value: { lock, unlock, type: "portrait-primary" },
    });
    (HTMLElement.prototype as unknown as { requestFullscreen: () => Promise<void> }).requestFullscreen =
      vi.fn(() => Promise.resolve());
    return { lock, unlock };
  }

  afterEach(() => {
    delete (HTMLElement.prototype as unknown as { requestFullscreen?: unknown }).requestFullscreen;
    Object.defineProperty(document, "fullscreenEnabled", { configurable: true, value: undefined });
  });

  it("the Focus button locks landscape after true fullscreen on a touch screen, and unlocks on exit", async () => {
    const { lock, unlock } = fullscreenCapable();
    media({ landscape: false, coarse: true });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await userEvent.click(screen.getByTestId("focus-enter"));
    await waitFor(() => expect(root().dataset.focus).toBe("native"));
    expect(lock).toHaveBeenCalledWith("landscape");
    await userEvent.click(screen.getByTestId("focus-exit"));
    expect(unlock).toHaveBeenCalled();
  });

  it("a desktop's Focus locks nothing", async () => {
    const { lock } = fullscreenCapable();
    media({ landscape: false, coarse: false });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await userEvent.click(screen.getByTestId("focus-enter"));
    await waitFor(() => expect(root().dataset.focus).toBe("native"));
    expect(lock).not.toHaveBeenCalled();
  });
});
