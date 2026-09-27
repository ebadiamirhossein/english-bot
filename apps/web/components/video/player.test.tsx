import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SaveWordResult, VideoBlockPayload, WordLookup } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, reportVideoProgress: vi.fn(), saveWord: vi.fn(), lookupWord: vi.fn() };
});

const api = await import("@/lib/api");
const { VideoPlayer } = await import("./player");

/**
 * W13-i's client half.
 *
 * **What these assert that the Python suite cannot:** that no percentage is on
 * the screen, that L1 subtitles are off until asked for, that a purged
 * transcript still plays the video, and that the highlight marks the words the
 * server said were unknown and not a set this file re-derived.
 */

function payload(over: Partial<VideoBlockPayload> = {}): VideoBlockPayload {
  return {
    video_id: 11,
    youtube_id: "y_525lzqbg0",
    title: "A probe video",
    duration_s: 720,
    accent: "british",
    track: "life",
    resume_position_s: 0,
    completed: false,
    transcript_available: true,
    transcript: "we were talking about the rent again",
    // **Untimed by default: the THIRD STATE is the ordinary one.** Most pool
    // rows have a transcript and no cues until a refresh fills them, so the
    // fixture defaults to the case a learner is most likely to meet. W31b: the
    // server sends display lines, here one untimed sentence.
    lines: [{ start: null, end: null, text: "we were talking about the rent again" }],
    lines_timed: false,
    transcript_lang: "en",
    unknown_lemmas: ["rent"],
    coverage_band: "in",
    ...over,
  };
}

beforeEach(() => {
  vi.mocked(api.reportVideoProgress).mockReset();
  vi.mocked(api.reportVideoProgress).mockResolvedValue({
    video_id: 11,
    youtube_id: "y_525lzqbg0",
    title: null,
    duration_s: 720,
    resume_position_s: 0,
    completed: false,
  });
  // The IFrame API never loads in jsdom; the component must render everything
  // else regardless, which is what a learner on a slow connection also gets.
  (window as unknown as { YT?: unknown }).YT = undefined;
});

describe("the coverage badge", () => {
  it("shows a difficulty line and never a percentage", () => {
    const { container } = render(
      <VideoPlayer payload={payload()} l1Language="fa" />,
    );
    expect(screen.getByTestId("coverage-band").dataset.band).toBe("in");
    // **The claim the record cannot support.** #288's inflation is uncounted,
    // #334's `coverage_fit` returns 1.0 across the band, and #330's percentage
    // is over 234 characters. No digit-percent may reach a learner.
    expect(container.textContent).not.toMatch(/\d+\s*%/);
  });

  it("shows nothing at all when the server withheld the band", () => {
    render(<VideoPlayer payload={payload({ coverage_band: null })} l1Language="fa" />);
    expect(screen.queryByTestId("coverage-band")).toBeNull();
  });

  it("carries no verdict about the learner in any band", () => {
    for (const band of ["below", "in", "above"] as const) {
      const { container, unmount } = render(
        <VideoPlayer payload={payload({ coverage_band: band })} l1Language="fa" />,
      );
      expect(container.textContent).not.toMatch(
        /wrong|incorrect|failed|missed|too hard for you|behind/i,
      );
      unmount();
    }
  });
});

/**
 * **#353. THE TWO ASSERTIONS BELOW ARE INVERTED, NOT DELETED** — W10's own
 * precedent when home's `disabled` button was turned on: *a deleted assertion
 * is indistinguishable from one that was forgotten.* They read, until
 * 2026-09-02:
 *
 *   it("is off until the learner asks for it — PRD §7.3 and the row's criterion")
 *     → `toggle-l1` present, `aria-pressed` false, label contains "Show"
 *   it("names the language rather than saying “translation”")
 *     → label contains "LT", and after a click `aria-pressed` is "true"
 *
 * **BOTH PASSED OVER A CONTROL THAT DID NOTHING**, and the second is the more
 * instructive one: it clicked the button and asserted that `aria-pressed`
 * flipped — **which is the button's own state and not evidence that anything
 * appeared.** #345's shape, found in shipped code rather than in a new test.
 * There has never been an L1 track to show: PRD §2.5 says it is generated from
 * the English transcript and cached, never fetched from YouTube, and generating
 * it is gated on §1a.
 *
 * **So the control is gone until it can do something** — #353's second close,
 * not its first. A control that answers a tap by relabelling itself is worse
 * than an absent one: the learner cannot tell whether the feature is broken,
 * slow, or something they did wrong.
 */
describe("L1 subtitles", () => {
  it("offers no control while there is no track to show (#353)", () => {
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(screen.queryByTestId("toggle-l1")).toBeNull();
    // The positive control: the player DID render, so the absence above is the
    // control being gone and not the component failing to mount (#345).
    expect(screen.getByTestId("rate-0.75")).toBeInTheDocument();
  });

  it("shows no Show/Hide language affordance anywhere on the player", () => {
    const { container } = render(
      <VideoPlayer payload={payload()} l1Language="lt" />,
    );
    // Scanned over the whole player rather than by test-id, so re-adding the
    // affordance under a different id fails here too.
    //
    // **PLAIN SUBSTRINGS, AND THE FIRST DRAFT OF THIS LINE IS WHY.** It was
    // written as `not.toMatch(/\bShow LT\b/)` and PASSED against the live
    // control — `textContent` concatenates with no separator, so "Show LT" was
    // followed directly by the transcript's "we were talking" and the trailing
    // `\b` never matched. **An assertion that could not fail for the reason it
    // claimed** (#345), found in this slice's own new test.
    expect(container.textContent).not.toContain("Show LT");
    expect(container.textContent).not.toContain("Hide LT");
    // The positive control: the player rendered and this scan read it.
    expect(container.textContent).toContain("0.75×");
  });
});

describe("a purged transcript (#335)", () => {
  it("still renders the player and says only the follow-along text is gone", () => {
    render(
      <VideoPlayer
        payload={payload({
          transcript_available: false,
          transcript: null,
          unknown_lemmas: [],
          coverage_band: null,
        })}
        l1Language="fa"
      />,
    );
    expect(screen.getByTestId("video-player")).not.toBeNull();
    expect(screen.getByTestId("no-transcript")).not.toBeNull();
    expect(screen.queryByTestId("transcript")).toBeNull();
  });

  it("does not blame anyone and does not say the video expired", () => {
    const { container } = render(
      <VideoPlayer
        payload={payload({ transcript_available: false, transcript: null })}
        l1Language="fa"
      />,
    );
    expect(container.textContent).not.toMatch(
      /expired|sorry|unavailable|error|couldn’t|could not/i,
    );
  });
});

describe("playback speed", () => {
  it("offers 0.75× for the whole video", () => {
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(screen.getByTestId("rate-0.75")).not.toBeNull();
  });

  /**
   * **W31b, Q3: loop-line exists now, and only where there are line bounds.**
   * This test read *"offers no per-line control, because no per-cue timings
   * exist"* (R12) and asserted `loop-line` absent everywhere. Migration 021
   * stored the timings, and `core.video.lines` builds lines from whole cues;
   * the operator ruled loop-line in. **It is still absent where there are no
   * bounds** — an untimed transcript — which is the half of R12 that stands.
   * `line-rate` stays absent: YouTube has one rate per player (0.75× + loop).
   */
  it("offers no loop without timed lines, and never a per-line rate", () => {
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(screen.queryByTestId("loop-line")).toBeNull();
    expect(screen.queryByTestId("line-rate")).toBeNull();
  });
});

describe("the watch signal (#258, #291)", () => {
  it("offers no completion control — the ping is the log", () => {
    const { container } = render(
      <VideoPlayer payload={payload()} l1Language="fa" />,
    );
    expect(container.textContent).not.toMatch(
      /mark.*(done|watched|complete)|i.?ve watched it|finish/i,
    );
  });

  it("says so plainly once the server reports it watched", () => {
    render(<VideoPlayer payload={payload({ completed: true })} l1Language="fa" />);
    expect(screen.getByTestId("video-watched")).not.toBeNull();
  });

  /**
   * **The IFrame API is faked at the boundary the component actually uses** —
   * `window.YT.Player` — rather than by mocking the component's own callback.
   * A test that stubbed `ping` would assert that a function it wrote calls
   * itself. This one exercises the path a learner takes: watch, close the tab.
   */
  it("reports the last position on unmount so closing the tab keeps the place", async () => {
    const setPlaybackRate = vi.fn();
    // **W31a: the fake now fires `onReady`, as the real API always does.** It
    // had every method from birth and never readied, which is the one shape
    // the real player never has — and the shape that hid `ENGLISH-WEB-2`.
    (window as unknown as { YT: unknown }).YT = {
      Player: class {
        constructor(_el: HTMLElement, options: { events?: { onReady?: () => void } }) {
          queueMicrotask(() => options.events?.onReady?.());
        }
        getCurrentTime() {
          return 412.6;
        }
        setPlaybackRate = setPlaybackRate;
        destroy() {}
      },
    };

    const { unmount } = render(
      <VideoPlayer payload={payload()} l1Language="fa" />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("player-mount").dataset.playerReady).toBe("true"),
    );
    unmount();

    // The raw player time reaches the client function; `reportVideoProgress`
    // floors it on the way to the wire, because `resume_position_s` is an
    // INTEGER column and the rounding must be ours rather than Postgres's.
    await waitFor(() =>
      expect(vi.mocked(api.reportVideoProgress)).toHaveBeenCalledWith(11, 412.6),
    );
  });

  it("sends a position and never a completion verdict", async () => {
    (window as unknown as { YT: unknown }).YT = {
      Player: class {
        constructor(_el: HTMLElement, options: { events?: { onReady?: () => void } }) {
          queueMicrotask(() => options.events?.onReady?.());
        }
        getCurrentTime() {
          return 700;
        }
        setPlaybackRate() {}
        destroy() {}
      },
    };
    const { unmount } = render(
      <VideoPlayer payload={payload()} l1Language="fa" />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("player-mount").dataset.playerReady).toBe("true"),
    );
    unmount();
    // **The client cannot assert a video was finished (#190, #291).**
    // `core/video/watch.py` decides it from the position and the stored
    // duration; the call signature makes a client verdict unrepresentable.
    await waitFor(() => {
      const call = vi.mocked(api.reportVideoProgress).mock.calls.at(-1);
      expect(call).toEqual([11, 700]);
    });
  });
});

/**
 * W31b — the transcript as **lines** (the operator's ruling on #397).
 *
 * The tracks are **synthesised** (#175): the lines here are what
 * `core.video.lines` sends; the Python suite holds how they are built.
 */
const TIMED = {
  transcript: "hey how are you doing today [laughter] it was great",
  lines: [
    { start: 0, end: 2.4, text: "hey how are you" },
    { start: 2.4, end: 5.1, text: "doing today" },
    { start: 5.1, end: 8, text: "[laughter] it was great" },
  ],
  lines_timed: true,
};

describe("the transcript as lines", () => {
  it("is a list of lines, not a paragraph", () => {
    render(<VideoPlayer payload={payload(TIMED)} l1Language="fa" />);
    const rows = screen.getAllByTestId("line");
    expect(rows.map((r) => r.textContent)).toEqual([
      "0:00hey how are you",
      "0:02doing today",
      "0:05[laughter] it was great",
    ]);
  });

  it("marks the words the SERVER said were unknown, and invents none", () => {
    render(
      <VideoPlayer
        payload={payload({
          lines: [{ start: null, end: null, text: "we were renting the rent" }],
          unknown_lemmas: ["rent"],
        })}
        l1Language="fa"
      />,
    );
    // "renting" is not marked: no lemmatising on the client (W13-i's rule).
    expect(screen.getAllByTestId("unknown-word").map((n) => n.textContent)).toEqual(["rent"]);
  });

  it("renders a sound tag dimmed and not tappable", () => {
    render(<VideoPlayer payload={payload(TIMED)} l1Language="fa" />);
    const tags = screen.getAllByTestId("sound-tag");
    expect(tags[0].textContent).toBe("[laughter]");
    expect(tags[0].tagName).toBe("SPAN");
    expect(screen.queryByRole("button", { name: "laughter" })).toBeNull();
  });

  it("shows untimed lines without times, without a current line, without a loop", () => {
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    expect(screen.getAllByTestId("line")).toHaveLength(1);
    expect(screen.queryByTestId("line-seek")).toBeNull();
    expect(screen.queryByTestId("subtitle-block")).toBeNull();
    // Nothing tells the learner a highlight is missing.
    expect(screen.getByTestId("video-player").textContent).not.toMatch(/timed|sync|highlight/i);
  });
});

describe("the synced line", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  function watchAt(time: number) {
    vi.useFakeTimers();
    const instances = fakeIframeApi();
    render(<VideoPlayer payload={payload(TIMED)} l1Language="fa" />);
    act(() => instances[0].fireReady(time));
    act(() => vi.advanceTimersByTime(300));
    return instances[0];
  }

  it("shows the line being spoken large, with the ones either side dimmed", () => {
    watchAt(3.0);
    expect(screen.getByTestId("subtitle-now").textContent).toBe("doing today");
    expect(screen.getByTestId("subtitle-prev").textContent).toBe("hey how are you");
    expect(screen.getByTestId("subtitle-next").textContent).toBe("[laughter] it was great");
  });

  it("highlights the active line in the list, and only that one", () => {
    watchAt(3.0);
    const rows = screen.getAllByTestId("line");
    expect(rows.map((r) => r.dataset.active ?? null)).toEqual([null, "true", null]);
    // Real styling, not an unread data attribute (#467).
    expect(rows[1].className).toMatch(/bg-primary/);
  });

  it("shows nothing as spoken before the first line starts", () => {
    watchAt(-1);
    expect(screen.getByTestId("subtitle-now").textContent).toBe("");
    expect(screen.getByTestId("subtitle-next").textContent).toBe("hey how are you");
  });

  it("keeps the last line through the caption tail", () => {
    watchAt(900);
    expect(screen.getByTestId("subtitle-now").textContent).toBe("[laughter] it was great");
  });

  it("seeks to a line when its time is tapped", () => {
    const fake = watchAt(0.5);
    act(() => {
      screen.getAllByTestId("line-seek")[2].click();
    });
    expect(fake.seekTo).toHaveBeenCalledWith(5.1, true);
  });

  it("loops the current line: past its end, back to its start", () => {
    const fake = watchAt(3.0);
    act(() => {
      screen.getByTestId("loop-line").click();
    });
    expect(screen.getByTestId("loop-line").getAttribute("aria-pressed")).toBe("true");
    fake.time = 5.2; // past "doing today"'s end (5.1)
    act(() => vi.advanceTimersByTime(300));
    expect(fake.seekTo).toHaveBeenCalledWith(2.4, true);
    act(() => {
      screen.getByTestId("loop-line").click();
    });
    fake.seekTo.mockClear();
    fake.time = 5.2;
    act(() => vi.advanceTimersByTime(300));
    expect(fake.seekTo).not.toHaveBeenCalled();
  });

  it("a word tap pauses a playing video", () => {
    const fake = watchAt(1.0);
    vi.mocked(api.lookupWord).mockReturnValue(new Promise(() => {}));
    act(() => {
      screen.getAllByTestId("known-word")[0].click();
    });
    expect(fake.pauseVideo).toHaveBeenCalledTimes(1);
  });
});

describe("pause to read, on a desktop pointer (C5)", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  function desktop(matches: boolean) {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches,
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }));
    (window as unknown as { matchMedia: unknown }).matchMedia = globalThis.matchMedia;
  }

  function watching() {
    vi.useFakeTimers();
    const instances = fakeIframeApi();
    render(<VideoPlayer payload={payload(TIMED)} l1Language="fa" />);
    act(() => instances[0].fireReady(3.0));
    return instances[0];
  }

  it("pauses while the pointer is on the current line, and resumes after", () => {
    desktop(true);
    const fake = watching();
    fireEvent.mouseEnter(screen.getByTestId("subtitle-block"));
    expect(fake.pauseVideo).toHaveBeenCalledTimes(1);
    fireEvent.mouseLeave(screen.getByTestId("subtitle-block"));
    expect(fake.playVideo).toHaveBeenCalledTimes(1);
  });

  it("does not pause over the line list", () => {
    desktop(true);
    const fake = watching();
    fireEvent.mouseEnter(screen.getByTestId("line-list"));
    fireEvent.mouseOver(screen.getAllByTestId("line")[1]);
    expect(fake.pauseVideo).not.toHaveBeenCalled();
  });

  it("does not resume a video the learner had paused themselves", () => {
    desktop(true);
    const fake = watching();
    fake.state = 2; // paused already
    fireEvent.mouseEnter(screen.getByTestId("subtitle-block"));
    fireEvent.mouseLeave(screen.getByTestId("subtitle-block"));
    expect(fake.pauseVideo).not.toHaveBeenCalled();
    expect(fake.playVideo).not.toHaveBeenCalled();
  });

  it("while the word sheet is open, leaving the line does not resume; closing it does", async () => {
    desktop(true);
    vi.mocked(api.lookupWord).mockResolvedValue({ ...RENT, word: "doing", lemma: "do" });
    const fake = watching();
    vi.useRealTimers();
    fireEvent.mouseEnter(screen.getByTestId("subtitle-block"));
    expect(fake.pauseVideo).toHaveBeenCalledTimes(1);
    act(() => {
      screen.getByTestId("subtitle-now").querySelector("button")!.click();
    });
    await screen.findByTestId("word-sheet");
    fireEvent.mouseLeave(screen.getByTestId("subtitle-block"));
    expect(fake.playVideo).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("word-sheet-close"));
    expect(fake.playVideo).toHaveBeenCalledTimes(1);
  });

  it("does nothing on hover without a hovering pointer (a phone)", () => {
    desktop(false);
    const fake = watching();
    fireEvent.mouseEnter(screen.getByTestId("subtitle-block"));
    expect(fake.pauseVideo).not.toHaveBeenCalled();
  });
});

describe("Focus", () => {
  it("fills the screen with the player and the line, where the browser has no element fullscreen", async () => {
    render(<VideoPlayer payload={payload(TIMED)} l1Language="fa" />);
    await userEvent.click(screen.getByTestId("focus-enter"));
    const root = screen.getByTestId("video-player");
    // jsdom has no Fullscreen API: the fixed full-viewport layout (iPhone's).
    expect(root.dataset.focus).toBe("fixed");
    expect(root.className).toMatch(/fixed inset-0/);
    expect(screen.getByTestId("subtitle-block")).toBeInTheDocument();
    expect(screen.queryByTestId("line-list")).toBeNull();
    await userEvent.click(screen.getByTestId("focus-exit"));
    expect(screen.getByTestId("video-player").dataset.focus).toBe("off");
  });

  it("says plainly when a video has no timed subtitles to show", async () => {
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await userEvent.click(screen.getByTestId("focus-enter"));
    expect(screen.getByTestId("no-timed")).toHaveTextContent(
      "This video has no timed subtitles.",
    );
  });

  it("asks YouTube to turn off its own fullscreen and play inline", () => {
    const instances = fakeIframeApi();
    render(<VideoPlayer payload={payload(TIMED)} l1Language="fa" />);
    const vars = instances[0].options.playerVars as Record<string, unknown>;
    expect(vars.fs).toBe(0);
    expect(vars.playsinline).toBe(1);
  });
});

/**
 * W13-ii → **W31c — the tap opens the WORD SHEET, and Save is in it.**
 *
 * W13-ii saved on the tap and printed one line; the operator's reference
 * (Trancy / Language Reactor) is *tap, see what it is, keep it*. The W13-ii and
 * W31a assertions below are carried into the sheet, not dropped: #178's
 * *already saved is not an error*, the anti-optimistic Save, and every refused
 * outcome's own sentence.
 */
const RENT: WordLookup = {
  word: "rent",
  lemma: "rent",
  line: "we were talking about the rent again",
  meaning: {
    definition: "money you pay to live somewhere",
    register: "neutral",
    l1: "اجاره",
    l1_language: "fa",
  },
  saved: "none",
};

describe("the word sheet", () => {
  beforeEach(() => {
    vi.mocked(api.saveWord).mockReset();
    vi.mocked(api.lookupWord).mockReset();
    vi.mocked(api.lookupWord).mockResolvedValue(RENT);
  });

  async function openSheet(lookup: WordLookup = RENT) {
    vi.mocked(api.lookupWord).mockResolvedValue(lookup);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await userEvent.click(screen.getByText("rent"));
    await screen.findByTestId("word-sheet");
  }

  async function save(result: SaveWordResult | Error) {
    if (result instanceof Error) vi.mocked(api.saveWord).mockRejectedValue(result);
    else vi.mocked(api.saveWord).mockResolvedValue(result);
    await userEvent.click(await screen.findByTestId("word-sheet-save"));
    return screen.findByTestId("save-word-result");
  }

  it("opens on a tap with the word, its line, the meaning and the learner's own language", async () => {
    await openSheet();
    expect(screen.getByTestId("word-sheet-word")).toHaveTextContent("rent");
    expect(await screen.findByTestId("word-sheet-line")).toHaveTextContent(
      "we were talking about the rent again",
    );
    expect(screen.getByTestId("word-sheet-meaning")).toHaveTextContent(
      "money you pay to live somewhere",
    );
    const l1 = screen.getByTestId("word-sheet-l1");
    expect(l1).toHaveTextContent("اجاره");
    expect(l1.getAttribute("dir")).toBe("rtl");
    expect(l1.getAttribute("lang")).toBe("fa");
  });

  it("asks with the line's INDEX, and never sends the line's text", async () => {
    await openSheet();
    expect(vi.mocked(api.lookupWord)).toHaveBeenCalledWith(11, "rent", 0);
    await save({ state: "saved", card_ids: [1, 2] });
    expect(vi.mocked(api.saveWord)).toHaveBeenCalledWith(11, "rent", 0);
  });

  it("saves nothing until Save is pressed", async () => {
    await openSheet();
    await screen.findByTestId("word-sheet-save");
    expect(vi.mocked(api.saveWord)).not.toHaveBeenCalled();
    expect(screen.queryByTestId("save-word-result")).toBeNull();
  });

  it("confirms a save", async () => {
    await openSheet();
    expect(await save({ state: "saved", card_ids: [1, 2] })).toHaveTextContent(
      "Added to your deck.",
    );
  });

  it("says already saved without saying anything went wrong (#178)", async () => {
    await openSheet();
    const message = await save({ state: "already_saved", card_ids: [] });
    expect(message).toHaveTextContent("Already in your deck.");
    expect(message.className).not.toMatch(/destructive|error|red/);
  });

  it("offers Save for a word nobody has explained yet — the operator's finding", async () => {
    await openSheet({ ...RENT, meaning: undefined });
    expect(await screen.findByTestId("word-sheet-no-meaning")).toHaveTextContent(
      "No meaning for this one yet — you can still save it.",
    );
    expect(await save({ state: "pending", card_ids: [], meaning_soon: true })).toHaveTextContent(
      "Saved. The meaning will be ready soon.",
    );
  });

  it("does not promise a meaning while nothing will fill it (C4)", async () => {
    await openSheet({ ...RENT, meaning: undefined });
    expect(await save({ state: "pending", card_ids: [], meaning_soon: false })).toHaveTextContent(
      "Saved to your words. Its meaning isn’t ready yet.",
    );
  });

  it("shows a word that is already kept as kept, with no Save", async () => {
    await openSheet({ ...RENT, saved: "in_deck" });
    expect(await screen.findByTestId("word-sheet-kept")).toHaveTextContent("In your words.");
    expect(screen.queryByTestId("word-sheet-save")).toBeNull();
  });

  it.each([
    [404, "This video isn’t in your list any more.", false],
    [429, "That’s a lot of words at once — try again in a minute.", true],
    [422, "That didn’t go through on our side — not yours. Try again in a moment.", true],
    [500, "That didn’t go through on our side — not yours. Try again in a moment.", true],
  ])("says what a %i means, and keeps Save only where trying again helps", async (status, copy, retry) => {
    await openSheet();
    const message = await save(new api.ApiError("x", status));
    expect(message).toHaveTextContent(copy);
    expect(Boolean(screen.queryByTestId("word-sheet-save"))).toBe(retry);
  });

  it("says a dropped connection is a connection, not a refusal", async () => {
    await openSheet();
    expect(await save(new api.ApiError("Could not reach the API"))).toHaveTextContent(
      "Couldn’t reach the server. Check your connection and tap again.",
    );
  });

  it("never shows W13-ii's old catch-all line", async () => {
    for (const status of [404, 422, 429, 500, undefined]) {
      const { unmount } = render(<VideoPlayer payload={payload()} l1Language="fa" />);
      await userEvent.click(screen.getByText("rent"));
      vi.mocked(api.saveWord).mockRejectedValue(new api.ApiError("x", status));
      await userEvent.click(await screen.findByTestId("word-sheet-save"));
      expect(await screen.findByTestId("save-word-result")).not.toHaveTextContent(
        "Could not add that just now.",
      );
      unmount();
    }
  });

  it("does not claim a save before the server has answered", async () => {
    await openSheet();
    vi.mocked(api.saveWord).mockReturnValue(new Promise(() => {}));
    await userEvent.click(await screen.findByTestId("word-sheet-save"));
    expect(screen.queryByTestId("save-word-result")).toBeNull();
  });

  it("shows an approved picture with its credit (Q9 (C))", async () => {
    await openSheet({
      ...RENT,
      image: {
        id: 7, ext: "jpg", width: 330, height: 220, alt: "rent",
        author: "A. Photographer", licence: "CC BY 4.0",
        licence_url: "https://creativecommons.org/licenses/by/4.0/",
        source_url: "https://commons.wikimedia.org/wiki/File:Example.jpg",
      },
    });
    const figure = await screen.findByTestId("card-image");
    expect(figure).toHaveTextContent("A. Photographer");
    expect(figure).toHaveTextContent("CC BY 4.0");
  });

  it("closes on Escape and on the backdrop", async () => {
    await openSheet();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByTestId("word-sheet")).toBeNull();
    await userEvent.click(screen.getByText("rent"));
    await screen.findByTestId("word-sheet");
    await userEvent.click(screen.getByTestId("word-sheet-backdrop"));
    expect(screen.queryByTestId("word-sheet")).toBeNull();
  });
});

/**
 * W31a — **`ENGLISH-WEB-2`**: an unhandled `TypeError` with no message, user 3,
 * the frame `setInterval(() => { … e.getCurrentTime() … }, 250)`.
 *
 * **The IFrame API attaches `getCurrentTime` and friends only when the player
 * is ready** — `new YT.Player(...)` returns at once and the methods arrive with
 * `onReady`. The player passed no `onReady` and started its 250 ms clock on
 * mount, so every tick between the constructor and the iframe loading threw.
 * The fakes below model that, which the older fakes in this file did not: they
 * had every method from birth, so they could not see the defect.
 */
type FakeInstance = {
  el: HTMLElement;
  options: { events?: { onReady?: (e: unknown) => void } } & Record<string, unknown>;
  getCurrentTime?: ReturnType<typeof vi.fn>;
  setPlaybackRate?: ReturnType<typeof vi.fn>;
  pauseVideo: ReturnType<typeof vi.fn>;
  playVideo: ReturnType<typeof vi.fn>;
  seekTo: ReturnType<typeof vi.fn>;
  getPlayerState?: ReturnType<typeof vi.fn>;
  destroy: ReturnType<typeof vi.fn>;
  time: number;
  state: number;
  fireReady: (time?: number) => void;
};

function fakeIframeApi(): FakeInstance[] {
  const instances: FakeInstance[] = [];
  class FakePlayer {
    el: HTMLElement;
    options: FakeInstance["options"];
    getCurrentTime?: ReturnType<typeof vi.fn>;
    setPlaybackRate?: ReturnType<typeof vi.fn>;
    destroy = vi.fn();
    constructor(el: HTMLElement, options: FakeInstance["options"]) {
      this.el = el;
      this.options = options;
      instances.push(this as unknown as FakeInstance);
    }
    time = 0;
    state = 1;
    pauseVideo?: ReturnType<typeof vi.fn>;
    playVideo?: ReturnType<typeof vi.fn>;
    seekTo?: ReturnType<typeof vi.fn>;
    getPlayerState?: ReturnType<typeof vi.fn>;
    fireReady(time = 12) {
      this.time = time;
      this.getCurrentTime = vi.fn(() => this.time);
      this.setPlaybackRate = vi.fn();
      this.pauseVideo = vi.fn(() => {
        this.state = 2;
      });
      this.playVideo = vi.fn(() => {
        this.state = 1;
      });
      this.seekTo = vi.fn((s: number) => {
        this.time = s;
      });
      this.getPlayerState = vi.fn(() => this.state);
      this.options.events?.onReady?.({ target: this });
    }
  }
  (window as unknown as { YT: unknown }).YT = { Player: FakePlayer };
  return instances;
}

const CUED = {
  transcript: "hey how are you",
  lines: [{ start: 0, end: 3.5, text: "hey how are you" }],
  lines_timed: true,
};

describe("the player waits for the IFrame API to be ready (ENGLISH-WEB-2)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("reads no clock before onReady — the ticks that threw on production", async () => {
    vi.useFakeTimers();
    const instances = fakeIframeApi();
    render(<VideoPlayer payload={payload(CUED)} l1Language="fa" />);
    expect(instances).toHaveLength(1);
    // Before ready the fake has NO getCurrentTime, exactly like the real API.
    expect(() => vi.advanceTimersByTime(1000)).not.toThrow();
    act(() => instances[0].fireReady(3));
    act(() => vi.advanceTimersByTime(1000));
    // The positive control: once ready, the highlight clock does read it.
    expect(instances[0].getCurrentTime).toHaveBeenCalled();
  });

  it("never pings a position from a player that was never ready", async () => {
    // Closing the tab before the iframe loaded: there is no position to keep,
    // and reading one is the TypeError. Nothing is sent.
    fakeIframeApi();
    const { unmount } = render(<VideoPlayer payload={payload(CUED)} l1Language="fa" />);
    unmount();
    await Promise.resolve();
    expect(vi.mocked(api.reportVideoProgress)).not.toHaveBeenCalled();
  });

  it("stops reading the clock when the player goes away", () => {
    vi.useFakeTimers();
    const instances = fakeIframeApi();
    const { unmount } = render(<VideoPlayer payload={payload(CUED)} l1Language="fa" />);
    act(() => instances[0].fireReady(3));
    act(() => vi.advanceTimersByTime(500));
    unmount();
    const after = instances[0].getCurrentTime!.mock.calls.length;
    vi.advanceTimersByTime(5000);
    expect(instances[0].getCurrentTime!.mock.calls.length).toBe(after);
    expect(instances[0].destroy).toHaveBeenCalledTimes(1);
  });

  it("on a new video, drops the old clock and waits for the new player's onReady", () => {
    vi.useFakeTimers();
    const instances = fakeIframeApi();
    const { rerender } = render(<VideoPlayer payload={payload(CUED)} l1Language="fa" />);
    act(() => instances[0].fireReady(3));
    rerender(
      <VideoPlayer payload={payload({ ...CUED, youtube_id: "other_video" })} l1Language="fa" />,
    );
    expect(instances).toHaveLength(2);
    expect(instances[0].destroy).toHaveBeenCalledTimes(1);
    const oldCalls = instances[0].getCurrentTime!.mock.calls.length;
    // The new player is not ready: nothing may call into it, and nothing may
    // keep calling into the destroyed one.
    expect(() => vi.advanceTimersByTime(1000)).not.toThrow();
    expect(instances[0].getCurrentTime!.mock.calls.length).toBe(oldCalls);
    // A fresh element per player: the old one was handed to YT and replaced.
    expect(instances[1].el).not.toBe(instances[0].el);
    act(() => instances[1].fireReady(7));
    act(() => vi.advanceTimersByTime(500));
    expect(instances[1].getCurrentTime).toHaveBeenCalled();
  });

  it("asks YouTube for the ready event rather than guessing", () => {
    const instances = fakeIframeApi();
    render(<VideoPlayer payload={payload(CUED)} l1Language="fa" />);
    expect(typeof instances[0].options.events?.onReady).toBe("function");
  });
});
