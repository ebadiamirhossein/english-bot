/**
 * W14 / #367 — **the recorder must show that it is listening**, and #366's UI
 * half: a capture failure must not render as a result.
 *
 * **THE DEFECT THE DATABASE FOUND.** The reference sentence takes ~5 s to say.
 * The first two live attempts captured **11.90 s** and **7.61 s**, with
 * **completeness BELOW accuracy on both** (50 vs 52, 75 vs 82) — the signature
 * of dead air: what was said scored reasonably, and the reference went
 * uncompleted because the learner could not tell when recording started or
 * stopped. A third of attempt #1's audio was silence, and the F0 quota paid
 * for it.
 *
 * **NO NEW DEPENDENCY.** The level meter reads a Web Audio `AnalyserNode`,
 * which is the same API already used for `decodeAudioData`.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ShadowLine, rmsFromTimeDomain } from "./shadow";
import { SHADOW } from "./copy";
import { mic, mockAudio, polyfillBlobArrayBuffer } from "./audio-mocks";

const WORDS = [{ word: "hello", accuracy: 90, clean: true }];

polyfillBlobArrayBuffer();

describe("rmsFromTimeDomain", () => {
  it("is 0 for digital silence and rises with amplitude", () => {
    const silence = new Uint8Array(64).fill(128);
    expect(rmsFromTimeDomain(silence)).toBe(0);

    const quiet = new Uint8Array(64).map((_, i) => 128 + (i % 2 ? 8 : -8));
    const loud = new Uint8Array(64).map((_, i) => 128 + (i % 2 ? 64 : -64));
    expect(rmsFromTimeDomain(loud)).toBeGreaterThan(rmsFromTimeDomain(quiet));
    expect(rmsFromTimeDomain(quiet)).toBeGreaterThan(0);
  });

  it("is clamped to 0..1 so a hot mic cannot overflow the meter", () => {
    const clipped = new Uint8Array(64).map((_, i) => (i % 2 ? 255 : 0));
    const level = rmsFromTimeDomain(clipped);
    expect(level).toBeGreaterThan(0.9);
    expect(level).toBeLessThanOrEqual(1);
  });
});

describe("the recording state", () => {
  beforeEach(() => {
    mockAudio();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows a level meter, an elapsed counter and one stop control", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ShadowLine cardId={1} sentence="A line to say aloud." />);

    // **Nothing before: the idle state must not claim to be listening.**
    expect(screen.queryByTestId("shadow-level")).toBeNull();
    expect(screen.queryByTestId("shadow-elapsed")).toBeNull();

    await user.click(screen.getByTestId("shadow-record"));

    expect(screen.getByTestId("shadow-level")).toBeTruthy();
    expect(screen.getByTestId("shadow-elapsed")).toBeTruthy();
    // **ONE obvious stop control**, not a start that has quietly become a stop
    // among other buttons.
    //
    // **THE ASSERTION CHANGED IN THE SAME COMMIT THAT ADDED A SECOND BUTTON
    // (§B's *Hear it*), AND IT GOT STRONGER RATHER THAN WEAKER.** It counted
    // buttons; it now counts ENABLED buttons — because §B's control is
    // deliberately disabled while recording (playing the line into a live
    // microphone would score the learner on the synthesised voice). **The
    // intent is unchanged: while recording there is exactly one thing a learner
    // can press, and it stops.** Loosening this to *find the stop button among
    // several* would have thrown the property away to accommodate the change.
    const enabled = screen
      .getAllByRole("button")
      .filter((b) => !(b as HTMLButtonElement).disabled);
    expect(enabled).toHaveLength(1);
    expect(enabled[0]).toHaveTextContent(SHADOW.stop);
  });

  it("moves the meter with REAL input amplitude, not a fixed animation", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ShadowLine cardId={1} sentence="A line to say aloud." />);
    await user.click(screen.getByTestId("shadow-record"));

    mic.amplitude = 0;
    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    const quiet = Number(
      screen.getByTestId("shadow-level").getAttribute("data-level"),
    );

    mic.amplitude = 90;
    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    const loud = Number(
      screen.getByTestId("shadow-level").getAttribute("data-level"),
    );

    expect(quiet).toBe(0);
    expect(loud).toBeGreaterThan(quiet);
  });

  it("counts elapsed seconds while recording", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ShadowLine cardId={1} sentence="A line to say aloud." />);
    await user.click(screen.getByTestId("shadow-record"));

    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByTestId("shadow-elapsed").textContent).toContain("3");
  });

  it("tears the meter down on stop so nothing keeps reading the microphone", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ attempt_id: 1, words: WORDS, improved: null }),
      })),
    );
    render(<ShadowLine cardId={1} sentence="A line to say aloud." />);
    await user.click(screen.getByTestId("shadow-record"));
    await user.click(screen.getByTestId("shadow-record"));

    await waitFor(() => expect(screen.getByTestId("shadow-result")).toBeTruthy());
    expect(screen.queryByTestId("shadow-level")).toBeNull();
    expect(screen.queryByTestId("shadow-elapsed")).toBeNull();
  });
});

describe("a capture the app could not hear (#366)", () => {
  beforeEach(() => mockAudio());
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders 'not caught' and NEVER per-word colouring", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 422 })));
    const user = userEvent.setup();
    render(<ShadowLine cardId={1} sentence="A line to say aloud." />);
    await user.click(screen.getByTestId("shadow-record"));
    await user.click(screen.getByTestId("shadow-record"));

    await waitFor(() =>
      expect(screen.getByTestId("shadow-not-heard")).toBeTruthy(),
    );
    // **The whole point: no result, no colouring, no verdict on nothing.**
    expect(screen.queryByTestId("shadow-result")).toBeNull();
    expect(screen.getByTestId("shadow-not-heard")).toHaveTextContent(
      SHADOW.notHeard,
    );
  });

  it("puts the failure on the app and not on the learner", () => {
    // The banned-phrase scan covers the source file; this asserts the SHAPE the
    // scan cannot: the sentence must not be about what the learner did.
    expect(SHADOW.notHeard.toLowerCase()).toContain("didn");
    for (const blaming of ["you ", "your ", "again?", "louder", "speak up"]) {
      expect(SHADOW.notHeard.toLowerCase()).not.toContain(blaming);
    }
  });
});
