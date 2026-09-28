import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

/**
 * **W32f (B2), #487 — operator ruling 2026-09-28: in full screen the caption
 * goes in a strip BELOW the video, not on the picture.** YouTube's Required
 * Minimum Functionality forbids overlays on the embedded player except
 * playback controls; the ruling also answers Finding 2 (two lines of large
 * type over the picture on an iPhone held sideways).
 *
 * jsdom has no layout, so *below*, *on one or two lines* and *no overflow* are
 * Playwright's (`e2e/focus-strip.spec.ts`). This file holds the structure:
 * **the video's box holds the player and nothing of ours** — in Focus and out
 * of it — the strip is outside it, its words tap and hover as the line under
 * the player does, and the full-screen icon lives at the strip's right end.
 *
 * **Replaces W32d's "caption inside the video box" assertions** in
 * `focus-caption.test.tsx`, with the reason in the decisions log.
 *
 * **RED BEFORE THE CODE (2026-09-28, on `ca55e40`).**
 */

const MAP: MeaningsMap = {
  l1: "fa",
  entries: { model: { k: "w", r: "neutral", s: [["noun", "a small copy of something bigger", "ماکت"]] } },
  forms: {}, here: {}, names: [], saved: {}, images: {},
};

function payload(): VideoBlockPayload {
  return {
    video_id: 11, youtube_id: "y_525lzqbg0", title: "A probe video", duration_s: 60,
    accent: "british", track: "life", resume_position_s: 0, completed: false,
    transcript_available: true, transcript: "it's a model of one",
    lines: [{ start: 0, end: 30, text: "it's a model of one" }],
    lines_timed: true, transcript_lang: "en", unknown_lemmas: [], coverage_band: "in",
  };
}

function media({ touch }: { touch: boolean }) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("orientation: landscape")
      ? false
      : query.includes("pointer: coarse")
        ? touch
        : query.includes("hover: hover")
          ? !touch
          : false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

const made: { pauseVideo: ReturnType<typeof vi.fn>; ready: () => void }[] = [];
function fakePlayer() {
  made.length = 0;
  class FakePlayer {
    events: { onReady?: (e: unknown) => void };
    constructor(_el: HTMLElement, options: { events: FakePlayer["events"] }) {
      this.events = options.events;
      made.push(this as never);
    }
    getCurrentTime = vi.fn(() => 1);
    setPlaybackRate = vi.fn();
    pauseVideo = vi.fn();
    playVideo = vi.fn();
    seekTo = vi.fn();
    getPlayerState = vi.fn(() => 1);
    destroy = vi.fn();
    ready() {
      act(() => this.events.onReady?.({ target: this }));
    }
  }
  (window as unknown as { YT: unknown }).YT = { Player: FakePlayer };
}

beforeEach(() => {
  fakePlayer();
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
  (window as unknown as { YT?: unknown }).YT = undefined;
  delete document.documentElement.dataset.videoFocus;
});

async function ready() {
  render(<VideoPlayer payload={payload()} l1Language="fa" />);
  made[0].ready();
  await waitFor(() => expect(screen.getByTestId("video-player").dataset.meanings).toBe("ready"));
}

/** Everything inside the video's box that is not YouTube's mount. */
function oursOnThePicture(): Element[] {
  const box = screen.getByTestId("video-box");
  const mount = screen.getByTestId("player-mount");
  return Array.from(box.querySelectorAll("*")).filter((el) => el !== mount && !mount.contains(el));
}

describe("B2 — Focus: the caption in a strip under the video, nothing on the picture", () => {
  it("the strip is outside the video's box; the box holds only the player", async () => {
    media({ touch: true });
    await ready();
    await userEvent.click(screen.getByTestId("focus-enter"));
    const strip = screen.getByTestId("caption-strip");
    expect(screen.getByTestId("video-box").contains(strip)).toBe(false);
    expect(screen.queryByTestId("caption-layer")).toBeNull();
    expect(oursOnThePicture()).toEqual([]);
    expect(within(strip).getByTestId("subtitle-now")).toHaveTextContent("it's a model of one");
  });

  it("the strip comes after the video and before the controls row", async () => {
    media({ touch: true });
    await ready();
    await userEvent.click(screen.getByTestId("focus-enter"));
    const order = [
      screen.getByTestId("video-box"),
      screen.getByTestId("caption-strip"),
      screen.getByTestId("focus-exit"),
    ];
    for (let i = 1; i < order.length; i += 1) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it("a word in the strip opens the sheet (a tap)", async () => {
    media({ touch: true });
    await ready();
    await userEvent.click(screen.getByTestId("focus-enter"));
    await userEvent.click(within(screen.getByTestId("caption-strip")).getByRole("button", { name: "model" }));
    expect(await screen.findByTestId("word-sheet")).toBeInTheDocument();
  });

  it("hovering the strip pauses, as the line under the player does (C5)", async () => {
    media({ touch: false });
    await ready();
    await userEvent.click(screen.getByTestId("focus-enter"));
    fireEvent.mouseEnter(within(screen.getByTestId("caption-strip")).getByTestId("subtitle-block"));
    expect(made[0].pauseVideo).toHaveBeenCalledTimes(1);
  });

  it("the strip's text is sized with the viewport, not a fixed large size", async () => {
    media({ touch: true });
    await ready();
    await userEvent.click(screen.getByTestId("focus-enter"));
    const now = within(screen.getByTestId("caption-strip")).getByTestId("subtitle-now");
    expect(now.className).toMatch(/caption-strip-text/);
    expect(now.className).not.toMatch(/text-2xl|sm:text-2xl/);
  });
});

describe("B2 / #486 — the full-screen icon is at the strip's right end, off the picture", () => {
  it("outside Focus: nothing of ours on the picture; the icon ends the line's row, under the video", async () => {
    media({ touch: true });
    await ready();
    expect(oursOnThePicture()).toEqual([]);
    const corner = screen.getByTestId("focus-corner");
    const row = screen.getByTestId("line-row");
    expect(row.contains(corner)).toBe(true);
    expect(row.lastElementChild).toBe(corner);
    expect(row.contains(screen.getByTestId("subtitle-block"))).toBe(true);
    expect(screen.getByTestId("video-box").contains(corner)).toBe(false);
    expect(corner).toHaveAccessibleName("Full screen");
    await userEvent.click(corner);
    expect(screen.getByTestId("video-player").dataset.focus).not.toBe("off");
  });

  it("pointing at the icon never pauses — it is beside the line block, not in it (C5)", async () => {
    media({ touch: false });
    await ready();
    const corner = screen.getByTestId("focus-corner");
    expect(screen.getByTestId("subtitle-block").contains(corner)).toBe(false);
    fireEvent.mouseEnter(corner);
    expect(made[0].pauseVideo).not.toHaveBeenCalled();
  });
});
