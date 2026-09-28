import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  };
});

const api = await import("@/lib/api");
const { VideoPlayer } = await import("./player");

/**
 * **W32b — instant meaning.** The operator, 2026-09-27: hovering (desktop) or
 * tapping (phone) ANY word shows its meaning in under a second. The map
 * arrives once when the page loads; after that a hover or a tap is a lookup
 * with no request at all — asserted here by counting the API calls, and in
 * Playwright with the network blocked.
 *
 * **RED BEFORE THE CODE (2026-09-28):** no map was fetched, no popover
 * existed, and the sheet always asked `lookupWord`.
 */

const MAP: MeaningsMap = {
  l1: "fa",
  entries: {
    party: { k: "w", r: "neutral", s: [["noun", "a social event", "مهمانی"]] },
    move: {
      k: "w",
      r: "neutral",
      s: [
        ["verb", "to take something to a different place", "جابه‌جا کردن"],
        ["verb", "to go to live somewhere else", "اسباب‌کشی کردن"],
      ],
    },
    ross: { k: "n" },
  },
  forms: { parties: "party", moving: "move" },
  here: { band: { d: "a group that plays music together", r: "neutral", l1: "گروه موسیقی" } },
  names: ["ross"],
  saved: {},
  images: {},
};

const LINES = {
  transcript: "moving the parties. ross and the band. a big van",
  lines: [
    { start: 0, end: 2, text: "moving the parties." },
    { start: 2, end: 4, text: "Ross and the band." },
    { start: 4, end: 6, text: "a big van" },
  ],
  lines_timed: true,
};

function payload(over: Partial<VideoBlockPayload> = {}): VideoBlockPayload {
  return {
    video_id: 11,
    youtube_id: "y_525lzqbg0",
    title: "A probe video",
    duration_s: 60,
    accent: "british",
    track: "life",
    resume_position_s: 0,
    completed: false,
    transcript_available: true,
    transcript: LINES.transcript,
    lines: LINES.lines,
    lines_timed: true,
    transcript_lang: "en",
    unknown_lemmas: [],
    coverage_band: "in",
    ...over,
  };
}

function pointer(hover: boolean) {
  // W32d: the stub answers per QUERY — a hovering pointer is never a turned phone.
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("orientation") ? false : hover,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
  (window as unknown as { matchMedia: unknown }).matchMedia = globalThis.matchMedia;
}

type Fake = { pauseVideo: ReturnType<typeof vi.fn>; playVideo: ReturnType<typeof vi.fn> };

function fakeYouTube(): Fake[] {
  const made: Fake[] = [];
  class Player {
    state = 1;
    pauseVideo = vi.fn(() => {
      this.state = 2;
    });
    playVideo = vi.fn(() => {
      this.state = 1;
    });
    getPlayerState = vi.fn(() => this.state);
    getCurrentTime = vi.fn(() => 0.5);
    seekTo = vi.fn();
    setPlaybackRate = vi.fn();
    destroy = vi.fn();
    constructor(_el: HTMLElement, options: { events?: { onReady?: () => void } }) {
      made.push(this);
      setTimeout(() => options.events?.onReady?.(), 0);
    }
  }
  (window as unknown as { YT: unknown }).YT = { Player };
  return made;
}

/** A word button in the line list (the list never pauses, C5). */
function listWord(text: string): HTMLElement {
  return within(screen.getByTestId("line-list")).getAllByRole("button", { name: text })[0];
}

beforeEach(() => {
  vi.mocked(api.reportVideoProgress).mockReset();
  vi.mocked(api.reportVideoProgress).mockResolvedValue({
    video_id: 11,
    youtube_id: "y_525lzqbg0",
    title: null,
    duration_s: 60,
    resume_position_s: 0,
    completed: false,
  });
  vi.mocked(api.lookupWord).mockReset();
  vi.mocked(api.saveWord).mockReset();
  vi.mocked(api.videoMeanings).mockReset();
  vi.mocked(api.videoMeanings).mockResolvedValue(MAP);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete (window as unknown as { YT?: unknown }).YT;
});

async function mapLoaded() {
  await waitFor(() =>
    expect(screen.getByTestId("video-player").getAttribute("data-meanings")).toBe("ready"),
  );
}

describe("the map", () => {
  it("is fetched once, when the page opens", async () => {
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    expect(vi.mocked(api.videoMeanings)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(api.videoMeanings)).toHaveBeenCalledWith(11);
  });

  it("is not fetched for a video with no text", async () => {
    render(
      <VideoPlayer
        payload={payload({ transcript_available: false, transcript: null, lines: [] })}
        l1Language="fa"
      />,
    );
    await act(async () => {});
    expect(vi.mocked(api.videoMeanings)).not.toHaveBeenCalled();
  });
});

describe("the popover, on a desktop pointer", () => {
  it("appears after 250 ms on a word, with the first sense and the learner's language", async () => {
    pointer(true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    vi.useFakeTimers();
    fireEvent.mouseEnter(listWord("moving"));
    act(() => vi.advanceTimersByTime(249));
    expect(screen.queryByTestId("word-popover")).toBeNull();
    act(() => vi.advanceTimersByTime(1));
    const popover = screen.getByTestId("word-popover");
    expect(popover).toHaveTextContent("moving");
    expect(popover).toHaveTextContent("to take something to a different place");
    expect(popover).not.toHaveTextContent("to go to live somewhere else");
    const l1 = within(popover).getByTestId("word-popover-l1");
    expect(l1).toHaveTextContent("جابه‌جا کردن");
    expect(l1.getAttribute("dir")).toBe("rtl");
    expect(popover.getAttribute("role")).toBe("tooltip");
    // **No request on hover.** The map was the only one.
    expect(vi.mocked(api.lookupWord)).not.toHaveBeenCalled();
    expect(vi.mocked(api.videoMeanings)).toHaveBeenCalledTimes(1);
  });

  it("does not flicker while the pointer passes over words", async () => {
    pointer(true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    vi.useFakeTimers();
    fireEvent.mouseEnter(listWord("moving"));
    act(() => vi.advanceTimersByTime(100));
    fireEvent.mouseLeave(listWord("moving"));
    fireEvent.mouseEnter(listWord("the"));
    act(() => vi.advanceTimersByTime(100));
    fireEvent.mouseLeave(listWord("the"));
    act(() => vi.advanceTimersByTime(500));
    expect(screen.queryByTestId("word-popover")).toBeNull();
  });

  it("once showing, follows the pointer to the next word at once (the skip delay)", async () => {
    pointer(true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    vi.useFakeTimers();
    fireEvent.mouseEnter(listWord("moving"));
    act(() => vi.advanceTimersByTime(250));
    fireEvent.mouseLeave(listWord("moving"));
    fireEvent.mouseEnter(listWord("parties"));
    expect(screen.getByTestId("word-popover")).toHaveTextContent("a social event");
  });

  it("shows the video's own meaning first, labelled here", async () => {
    pointer(true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    vi.useFakeTimers();
    fireEvent.mouseEnter(listWord("band"));
    act(() => vi.advanceTimersByTime(250));
    const popover = screen.getByTestId("word-popover");
    expect(within(popover).getByTestId("word-popover-here")).toHaveTextContent("here");
    expect(popover).toHaveTextContent("a group that plays music together");
  });

  it("says a name is a name, and a word with no entry has no meaning stored", async () => {
    pointer(true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    vi.useFakeTimers();
    fireEvent.mouseEnter(listWord("Ross"));
    act(() => vi.advanceTimersByTime(250));
    expect(screen.getByTestId("word-popover")).toHaveTextContent("a name");
    fireEvent.mouseLeave(listWord("Ross"));
    fireEvent.mouseEnter(listWord("van"));
    expect(screen.getByTestId("word-popover-miss")).toBeInTheDocument();
  });

  it("never pauses or plays the video — the block's hover-pause is unchanged (C5)", async () => {
    pointer(true);
    const made = fakeYouTube();
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    await waitFor(() =>
      expect(screen.getByTestId("player-mount").getAttribute("data-player-ready")).toBe("true"),
    );
    vi.useFakeTimers();
    // A word in the LIST: the popover shows; the video is untouched.
    fireEvent.mouseEnter(listWord("parties"));
    act(() => vi.advanceTimersByTime(300));
    expect(screen.getByTestId("word-popover")).toBeInTheDocument();
    expect(made[0].pauseVideo).not.toHaveBeenCalled();
    fireEvent.mouseLeave(listWord("parties"));
    // The CURRENT LINE: entering the block pauses (W31b), a word inside it adds
    // nothing, and leaving the word — not the block — resumes nothing.
    const block = screen.getByTestId("subtitle-block");
    fireEvent.mouseEnter(block);
    expect(made[0].pauseVideo).toHaveBeenCalledTimes(1);
    const word = within(screen.getByTestId("subtitle-now")).getByRole("button", { name: "moving" });
    fireEvent.mouseEnter(word, { relatedTarget: block });
    act(() => vi.advanceTimersByTime(300));
    // **Onto the block, not out of it** — what a real pointer does moving off a
    // word inside the line. Without `relatedTarget` React leaves every ancestor,
    // the block included, which no pointer inside the block ever does.
    fireEvent.mouseLeave(word, { relatedTarget: block });
    expect(made[0].pauseVideo).toHaveBeenCalledTimes(1);
    expect(made[0].playVideo).not.toHaveBeenCalled();
    fireEvent.mouseLeave(block);
    expect(made[0].playVideo).toHaveBeenCalledTimes(1);
  });

  it("does not appear on a phone, where a tap opens the sheet instead", async () => {
    pointer(false);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    vi.useFakeTimers();
    fireEvent.mouseEnter(listWord("moving"));
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.queryByTestId("word-popover")).toBeNull();
  });
});

describe("the sheet, from the map", () => {
  it("opens with the meaning already there — no request (the phone's tap)", async () => {
    pointer(false);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    await userEvent.click(listWord("moving"));
    const sheet = screen.getByTestId("word-sheet");
    expect(within(sheet).getByTestId("word-sheet-lemma")).toHaveTextContent("move");
    expect(within(sheet).getByTestId("word-sheet-line")).toHaveTextContent("moving the parties.");
    const senses = within(sheet).getAllByTestId("word-sheet-sense");
    expect(senses.map((s) => s.textContent)).toEqual([
      expect.stringContaining("to take something to a different place"),
      expect.stringContaining("to go to live somewhere else"),
    ]);
    expect(within(senses[0]).getByTestId("word-sheet-l1")).toHaveTextContent("جابه‌جا کردن");
    expect(within(sheet).getByTestId("word-sheet-save")).toBeEnabled();
    expect(vi.mocked(api.lookupWord)).not.toHaveBeenCalled();
  });

  it("puts here first, with the dictionary under it", async () => {
    vi.mocked(api.videoMeanings).mockResolvedValue({
      ...MAP,
      entries: { ...MAP.entries, band: { k: "w", r: "neutral", s: [["noun", "a musical group", "گروه"]] } },
    });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    await userEvent.click(listWord("band"));
    const sheet = screen.getByTestId("word-sheet");
    const here = within(sheet).getByTestId("word-sheet-here");
    expect(here).toHaveTextContent("a group that plays music together");
    expect(here.compareDocumentPosition(within(sheet).getAllByTestId("word-sheet-sense")[0]))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("says a name is a name", async () => {
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    await userEvent.click(listWord("Ross"));
    expect(screen.getByTestId("word-sheet-name")).toHaveTextContent("A name.");
  });

  it("saves, and the page then knows the word is kept", async () => {
    vi.mocked(api.saveWord).mockResolvedValue({ state: "saved", card_ids: [1, 2] });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await mapLoaded();
    await userEvent.click(listWord("parties"));
    await userEvent.click(screen.getByTestId("word-sheet-save"));
    expect(await screen.findByTestId("save-word-result")).toHaveTextContent("Added to your deck.");
    expect(vi.mocked(api.saveWord)).toHaveBeenCalledWith(11, "parties", 0);
    await userEvent.click(screen.getByTestId("word-sheet-close"));
    await userEvent.click(listWord("parties"));
    expect(screen.getByTestId("word-sheet-kept")).toHaveTextContent("In your words.");
    expect(vi.mocked(api.lookupWord)).not.toHaveBeenCalled();
  });

  it("falls back to asking the server when the map could not load", async () => {
    vi.mocked(api.videoMeanings).mockRejectedValue(new Error("offline"));
    vi.mocked(api.lookupWord).mockResolvedValue({
      word: "moving",
      lemma: "move",
      line: "moving the parties.",
      meaning: { definition: "to go", register: "neutral" },
      saved: "none",
    });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await waitFor(() =>
      expect(screen.getByTestId("video-player").getAttribute("data-meanings")).toBe("unavailable"),
    );
    await userEvent.click(listWord("moving"));
    expect(await screen.findByTestId("word-sheet-meaning")).toHaveTextContent("to go");
    expect(vi.mocked(api.lookupWord)).toHaveBeenCalledWith(11, "moving", 0);
  });
});
