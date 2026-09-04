/**
 * W14 test 11 — the browser half of the audio rule, and §2.6's ruling.
 *
 * **The disk rule has a browser side and it is not the server's.** A page that
 * offered the recording as a download, cached it in IndexedDB, or held it in
 * `localStorage` would break *audio is scored and discarded* just as surely as
 * a temp file on the server, and no Python test would notice.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ShadowLine, encodeWav, downmix } from "./shadow";
import { SHADOW } from "./copy";
import { mockAudio, polyfillBlobArrayBuffer } from "./audio-mocks";

polyfillBlobArrayBuffer();

const WORDS = [
  { word: "I'll", accuracy: 97, clean: true },
  { word: "grab", accuracy: 100, clean: true },
  { word: "the", accuracy: 62, clean: false },
];

describe("encodeWav", () => {
  it("writes a RIFF/WAVE header at the SOURCE rate — no resample (P0a)", () => {
    const blob = encodeWav(new Float32Array([0, 0.5]), 48000);
    expect(blob.type).toBe("audio/wav");
    // 44-byte header + 2 samples x 2 bytes.
    expect(blob.size).toBe(48);
  });

  it("downmixes stereo to one track by averaging", () => {
    const buffer = {
      numberOfChannels: 2,
      length: 2,
      getChannelData: (c: number) =>
        c === 0 ? new Float32Array([1, 0]) : new Float32Array([0, 1]),
    } as unknown as AudioBuffer;
    expect(Array.from(downmix(buffer))).toEqual([0.5, 0.5]);
  });
});

describe("ShadowLine", () => {
  beforeEach(() => {
    mockAudio();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows the sentence and never a score", async () => {
    render(<ShadowLine cardId={1} sentence="I'll grab the coffee." />);
    expect(screen.getByTestId("shadow-sentence")).toHaveTextContent(
      "I'll grab the coffee.",
    );
    expect(screen.getByTestId("shadow-record")).toHaveTextContent(SHADOW.start);
  });

  it("posts a WAV and colours the weak word without printing a number", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ attempt_id: 5, words: WORDS, improved: null }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<ShadowLine cardId={7} sentence="I'll grab the coffee." />);
    await user.click(screen.getByTestId("shadow-record")); // start
    await user.click(screen.getByTestId("shadow-record")); // stop

    await waitFor(() => expect(screen.getByTestId("shadow-result")).toBeTruthy());

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "audio/wav",
    );
    expect(init.credentials).toBe("include");

    const result = screen.getByTestId("shadow-result");
    // **The weak word is marked, and by a data attribute AND a class — colour
    // is never the only signal.**
    const weak = result.querySelectorAll('[data-weak="true"]');
    expect(weak).toHaveLength(1);
    expect(weak[0].textContent?.trim()).toBe("the");
    expect(weak[0].className).toContain("underline");
    // **NO NUMBER ANYWHERE.** 97, 100 and 62 are on the wire and none is shown.
    expect(result.textContent).not.toMatch(/\d/);
  });

  it("announces a raise and says nothing at all about a drop", async () => {
    for (const [improved, expected] of [
      [true, true],
      [null, false],
    ] as const) {
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => ({
          ok: true,
          status: 200,
          json: async () => ({ attempt_id: 1, words: WORDS, improved }),
        })),
      );
      const user = userEvent.setup();
      const view = render(<ShadowLine cardId={1} sentence="A line to say." />);
      await user.click(screen.getByTestId("shadow-record"));
      await user.click(screen.getByTestId("shadow-record"));
      await waitFor(() => expect(screen.getByTestId("shadow-result")).toBeTruthy());
      expect(screen.queryByText(SHADOW.improved) !== null).toBe(expected);
      view.unmount();
    }
  });

  it("says scoring is off on a 409 and does not read it as a bad attempt", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409 })));
    const user = userEvent.setup();
    render(<ShadowLine cardId={1} sentence="A line to say." />);
    await user.click(screen.getByTestId("shadow-record"));
    await user.click(screen.getByTestId("shadow-record"));
    await waitFor(() => expect(screen.getByTestId("shadow-off")).toBeTruthy());
    expect(screen.getByTestId("shadow-off")).toHaveTextContent(
      SHADOW.unavailable,
    );
    expect(screen.queryByTestId("shadow-result")).toBeNull();
  });

it("keeps the reference sentence visible and legible while recording (#367)", async () => {
    // **§C: THE LIKELIEST CAUSE OF THE EARLY STOP, REFUTED BY READING AND NOW
    // LOCKED BY A TEST.**
    //
    // Attempt 1 stopped at word 9 of 12, with the omissions contiguous at
    // positions 10-12. The obvious suspect was the recording UI replacing,
    // dimming or scrolling the sentence away. **It does not** — the result
    // replaces the sentence only at `phase === "done"`, and the meter is
    // appended BELOW it.
    //
    // **Nothing asserted that, which is #360's shape**: an invariant true by
    // construction with no instrument. This is the instrument. It does not fix
    // the early stop — **the cause remains unestablished** — it stops a later
    // slice from making the suspected cause real.
    const user = userEvent.setup();
    render(<ShadowLine cardId={1} sentence="I'll grab the coffee." />);
    await user.click(screen.getByTestId("shadow-record"));

    const line = screen.getByTestId("shadow-sentence");
    expect(line).toBeTruthy();
    expect(line.textContent).toBe("I'll grab the coffee.");
    // Not dimmed: no opacity/muted utility on the sentence while recording.
    expect(line.className).not.toMatch(/opacity-|text-muted/);
    // And the meter is present, so this is genuinely the recording phase.
    expect(screen.getByTestId("shadow-level")).toBeTruthy();
  });

  it("offers a listen control that is unavailable while recording", async () => {
    // **Playing the line into a live microphone would score the learner on the
    // synthesised voice.** The one state where this must not be tappable is
    // exactly the one a learner might reach for it in.
    const user = userEvent.setup();
    render(<ShadowLine cardId={1} sentence="A line to say." />);
    // **THE ASSERTION THAT WAS MISSING, AND WHY ROLE ALONE WOULD NOT HAVE
    // CAUGHT IT.** This asserted only testid, text and disabled-state — none of
    // which is *affordance* — and the control shipped as `variant="ghost"`,
    // rendering as bare text a learner would read as a label.
    //
    // **Adding `getByRole("button")` would NOT have caught it either: it WAS a
    // `<button>`.** The defect was invisible to every semantic query, because
    // it lived entirely in the variant. So the assertion is on
    // `data-variant`, which `Button` already exposes — checkable, and not the
    // brittle class-string assertion that would rot on a restyle.
    const listen = screen.getByRole("button", { name: SHADOW.listen });
    expect(listen).toHaveAttribute("data-testid", "shadow-listen");
    expect(listen).toHaveTextContent(SHADOW.listen);
    expect(listen).not.toBeDisabled();
    expect(listen).toHaveAttribute("data-variant", "outline");

    await user.click(screen.getByTestId("shadow-record"));
    expect(screen.getByTestId("shadow-listen")).toBeDisabled();
  });

  it("fetches the line audio on tap, never on load, and stores nothing", async () => {
    const createObjectURL = vi.fn(() => "blob:fake");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const play = vi.fn(async () => {});
    vi.stubGlobal(
      "Audio",
      class {
        onended: (() => void) | null = null;
        onerror: (() => void) | null = null;
        play = play;
      },
    );
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      blob: async () => new Blob([new Uint8Array([1])]),
    }));
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<ShadowLine cardId={9} sentence="A line to say." />);
    // **On load: nothing.** #106's no-cache flag makes every fetch a charge.
    expect(fetchMock).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("shadow-listen"));
    await waitFor(() => expect(play).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/shadow/9/audio");
    expect(init.credentials).toBe("include");
    // Never offered as a file: no download anchor, and the blob URL is revoked.
    expect(document.querySelectorAll("a[download]")).toHaveLength(0);
  });

  it("never offers the recording as a download or stores it", async () => {
    const createObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL });
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const indexedDBOpen = vi.fn();
    vi.stubGlobal("indexedDB", { open: indexedDBOpen });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({ attempt_id: 1, words: WORDS, improved: null }),
      })),
    );

    const user = userEvent.setup();
    const { container } = render(
      <ShadowLine cardId={1} sentence="A line to say." />,
    );
    await user.click(screen.getByTestId("shadow-record"));
    await user.click(screen.getByTestId("shadow-record"));
    await waitFor(() => expect(screen.getByTestId("shadow-result")).toBeTruthy());

    // **The audio existed in memory for one request and nowhere else.**
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(setItem).not.toHaveBeenCalled();
    expect(indexedDBOpen).not.toHaveBeenCalled();
    expect(container.querySelectorAll("a[download]")).toHaveLength(0);
  });
});
