import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { VideoBlockPayload } from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, reportVideoProgress: vi.fn() };
});

const api = await import("@/lib/api");
const { VideoPlayer } = await import("./player");
const { Transcript } = await import("./transcript");

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
    // **Null by default: the THIRD STATE is the ordinary one.** Most pool rows
    // have a transcript and no cues until a refresh fills them, so the fixture
    // defaults to the case a learner is most likely to meet.
    transcript_cues: null,
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

describe("L1 subtitles", () => {
  it("is off until the learner asks for it — PRD §7.3 and the row's criterion", () => {
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    const toggle = screen.getByTestId("toggle-l1");
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(toggle.textContent).toContain("Show");
  });

  it("names the language rather than saying “translation”", async () => {
    render(<VideoPlayer payload={payload()} l1Language="lt" />);
    expect(screen.getByTestId("toggle-l1").textContent).toContain("LT");
    await userEvent.click(screen.getByTestId("toggle-l1"));
    expect(screen.getByTestId("toggle-l1").getAttribute("aria-pressed")).toBe(
      "true",
    );
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
   * **R12, asserted so the absence is deliberate rather than forgotten.** No
   * per-cue timings are stored anywhere, so per-line speed, loop-a-line and the
   * follow-along highlight have no data behind them. They are HELD pending T5
   * and migration `021`, not dropped — and this test fails the day one of them
   * is added without the timings.
   */
  it("offers no per-line control, because no per-cue timings exist", () => {
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
    (window as unknown as { YT: unknown }).YT = {
      Player: class {
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

describe("the transcript", () => {
  it("marks the words the SERVER said were unknown", () => {
    render(
      <Transcript
        text="we were talking about the rent again"
        unknownLemmas={["rent"]}
        language="en"
      />,
    );
    const marked = screen.getAllByTestId("unknown-word").map((n) => n.textContent);
    expect(marked).toEqual(["rent"]);
  });

  /**
   * **It must not re-derive the set.** `unknown_lemmas` comes from
   * `core.lexicon`, which lemmatises against the seed list and the inflection
   * table; a cruder normaliser here would be a second instrument on one screen.
   * An inflected form whose lemma is unknown is simply not marked — erring
   * toward marking too LITTLE, which is the safe direction.
   */
  it("does not invent highlights the server did not send", () => {
    render(
      <Transcript
        text="we were renting the flat"
        unknownLemmas={["rent"]}
        language="en"
      />,
    );
    expect(screen.queryAllByTestId("unknown-word")).toHaveLength(0);
  });

  it("makes every word tappable, and a tap defines nothing yet (W13-ii)", async () => {
    const onWordTap = vi.fn();
    render(
      <Transcript
        text="we were talking"
        unknownLemmas={[]}
        language="en"
        onWordTap={onWordTap}
      />,
    );
    await userEvent.click(screen.getAllByTestId("known-word")[0]);
    expect(onWordTap).toHaveBeenCalledWith("we");
  });
});

/**
 * The synced highlight. **W13-i cue timings.**
 *
 * The tracks here are **synthesised** to the shape T5 measured — overlapping
 * windows, float seconds, a `start` on every element. **No committed fixture
 * holds anyone's subtitles** (#175), and it costs nothing: the property under
 * test is the overlap, not the content.
 */
describe("the synced highlight", () => {
  const ROLLING = [
    { text: "hey", start: 0.0, duration: 3.84 },
    { text: "how are you", start: 2.4, duration: 3.5 },
    { text: "doing today", start: 5.1, duration: 2.9 },
  ];
  const TEXT = "hey how are you doing today";

  it("lights the latest-started cue when two windows are live", () => {
    // At t=3.0 cue 0 (0→3.84) and cue 1 (2.4→5.9) are BOTH displayed.
    // The ruling picks the newer one, and it never reads `duration`.
    render(
      <Transcript
        text={TEXT}
        unknownLemmas={[]}
        language="en"
        cues={ROLLING}
        positionS={3.0}
      />,
    );
    expect(screen.getByTestId("cue-active").textContent).toBe("how are you");
  });

  it("lights nothing before the first cue starts", () => {
    render(
      <Transcript
        text={TEXT}
        unknownLemmas={[]}
        language="en"
        cues={ROLLING}
        positionS={-1}
      />,
    );
    expect(screen.queryByTestId("cue-active")).toBeNull();
  });

  it("keeps the last cue lit after it starts, through the caption tail", () => {
    // Captions end 15–22 s before the video does, so this tail is real.
    render(
      <Transcript
        text={TEXT}
        unknownLemmas={[]}
        language="en"
        cues={ROLLING}
        positionS={900}
      />,
    );
    expect(screen.getByTestId("cue-active").textContent).toBe("doing today");
  });

  it("renders the transcript unhighlighted when there are no cues", () => {
    // **The third state**: transcript present, cues absent. It renders, the
    // words stay tappable, and nothing tells the learner anything is missing.
    render(<Transcript text={TEXT} unknownLemmas={[]} language="en" />);
    expect(screen.getByTestId("transcript")).not.toBeNull();
    expect(screen.queryByTestId("cue-active")).toBeNull();
    expect(screen.getAllByTestId("known-word").length).toBeGreaterThan(0);
  });

  it("says nothing to the learner about a missing highlight", () => {
    const { container } = render(
      <Transcript text={TEXT} unknownLemmas={[]} language="en" />,
    );
    expect(container.textContent).toBe(TEXT);
  });
});
