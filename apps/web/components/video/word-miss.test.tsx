import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DefineWordResult, MeaningsMap, VideoBlockPayload } from "@/lib/api";

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
 * **W32c — a word the map has no entry for.** The sheet opens, says *Looking it
 * up…*, and fills in; the answer joins the page's map, so the next hover of
 * that word is instant. **Once per word per page** — a word whose lookup came
 * back empty is not asked about again. **Never on a hover.**
 *
 * **RED BEFORE THE CODE (2026-09-28):** the sheet said *no meaning yet* and
 * nothing was asked.
 */

const MAP: MeaningsMap = {
  l1: "fa",
  entries: { party: { k: "w", r: "neutral", s: [["noun", "a social event", "مهمانی"]] } },
  forms: { parties: "party" },
  here: {},
  names: [],
  saved: {},
  images: {},
};

function payload(): VideoBlockPayload {
  return {
    video_id: 11, youtube_id: "y_525lzqbg0", title: "A probe video", duration_s: 60,
    accent: "british", track: "life", resume_position_s: 0, completed: false,
    transcript_available: true, transcript: "the parties. a big van",
    lines: [
      { start: 0, end: 2, text: "the parties." },
      { start: 2, end: 4, text: "a big van" },
    ],
    lines_timed: true, transcript_lang: "en", unknown_lemmas: [], coverage_band: "in",
  };
}

function pointer(hover: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: hover, media: query, addEventListener() {}, removeEventListener() {},
  }));
  (window as unknown as { matchMedia: unknown }).matchMedia = globalThis.matchMedia;
}

function listWord(text: string): HTMLElement {
  return within(screen.getByTestId("line-list")).getAllByRole("button", { name: text })[0];
}

beforeEach(() => {
  vi.mocked(api.reportVideoProgress).mockReset();
  vi.mocked(api.reportVideoProgress).mockResolvedValue({
    video_id: 11, youtube_id: "y_525lzqbg0", title: null, duration_s: 60,
    resume_position_s: 0, completed: false,
  });
  vi.mocked(api.videoMeanings).mockReset();
  vi.mocked(api.videoMeanings).mockResolvedValue(MAP);
  vi.mocked(api.defineWord).mockReset();
  vi.mocked(api.lookupWord).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function open(word: string) {
  render(<VideoPlayer payload={payload()} l1Language="fa" />);
  await waitFor(() =>
    expect(screen.getByTestId("video-player").getAttribute("data-meanings")).toBe("ready"),
  );
  await userEvent.click(listWord(word));
}

describe("a miss, looked up once", () => {
  it("says Looking it up…, then fills in, and the word joins the page's map", async () => {
    let answer: (value: DefineWordResult) => void = () => {};
    vi.mocked(api.defineWord).mockReturnValue(new Promise((resolve) => (answer = resolve)));
    await open("van");
    expect(screen.getByTestId("word-sheet-looking")).toHaveTextContent("Looking it up…");
    expect(vi.mocked(api.defineWord)).toHaveBeenCalledWith(11, "van", 1, expect.any(AbortSignal));
    await act(async () =>
      answer({ state: "defined", entry: { k: "w", r: "neutral", s: [["noun", "a big car for goods", "ون"]] } }),
    );
    const sense = await screen.findByTestId("word-sheet-sense");
    expect(sense).toHaveTextContent("a big car for goods");
    expect(within(sense).getByTestId("word-sheet-l1")).toHaveTextContent("ون");
    expect(screen.getByTestId("word-sheet-save")).toBeEnabled();
    // Closed and reopened: the map has it now — no second request.
    await userEvent.click(screen.getByTestId("word-sheet-close"));
    await userEvent.click(listWord("van"));
    expect(screen.getByTestId("word-sheet-sense")).toHaveTextContent("a big car for goods");
    expect(vi.mocked(api.defineWord)).toHaveBeenCalledTimes(1);
  });

  it("a refused lookup reads no meaning yet, still offers Save, and is not asked again", async () => {
    vi.mocked(api.defineWord).mockResolvedValue({ state: "refused" });
    await open("van");
    expect(await screen.findByTestId("word-sheet-no-meaning")).toHaveTextContent(
      "No meaning for this one yet — you can still save it.",
    );
    expect(screen.getByTestId("word-sheet-save")).toBeEnabled();
    await userEvent.click(screen.getByTestId("word-sheet-close"));
    await userEvent.click(listWord("van"));
    expect(screen.getByTestId("word-sheet-no-meaning")).toBeInTheDocument();
    expect(vi.mocked(api.defineWord)).toHaveBeenCalledTimes(1);
  });

  it("a lookup that never answers gives up after twenty seconds", async () => {
    vi.mocked(api.defineWord).mockImplementation(
      (_v, _w, _l, signal) =>
        new Promise((_resolve, reject) => signal?.addEventListener("abort", () => reject(new Error("aborted")))),
    );
    // Fake timers from the start (the 20 s timer is scheduled on the click),
    // with real time still flowing so the page can load around them.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await waitFor(() =>
      expect(screen.getByTestId("video-player").getAttribute("data-meanings")).toBe("ready"),
    );
    fireEvent.click(listWord("van"));
    expect(screen.getByTestId("word-sheet-looking")).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(19_000);
    });
    expect(screen.getByTestId("word-sheet-looking")).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(1_000);
    });
    expect(await screen.findByTestId("word-sheet-no-meaning")).toBeInTheDocument();
  });

  it("a word the map holds is never looked up", async () => {
    await open("parties");
    expect(screen.getByTestId("word-sheet-sense")).toHaveTextContent("a social event");
    expect(vi.mocked(api.defineWord)).not.toHaveBeenCalled();
  });

  it("a hover never looks anything up", async () => {
    pointer(true);
    render(<VideoPlayer payload={payload()} l1Language="fa" />);
    await waitFor(() =>
      expect(screen.getByTestId("video-player").getAttribute("data-meanings")).toBe("ready"),
    );
    vi.useFakeTimers();
    fireEvent.mouseEnter(listWord("van"));
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByTestId("word-popover-miss")).toHaveTextContent("click to look it up");
    expect(vi.mocked(api.defineWord)).not.toHaveBeenCalled();
  });
});
