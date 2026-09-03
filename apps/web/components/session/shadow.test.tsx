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

// **jsdom's `Blob` has no `arrayBuffer()`; real browsers do.** Polyfilled here
// rather than worked around in the component: `Blob.prototype.arrayBuffer` is
// Safari 14+ and Chrome 76+, and the two learners are on an iPhone 17 and a
// Galaxy A34 — both far past it. **This is a test-environment gap, not a
// product one**, and the distinction is worth stating so nobody later "fixes"
// the component for a browser that does not exist.
if (typeof Blob.prototype.arrayBuffer !== "function") {
  Blob.prototype.arrayBuffer = async function arrayBuffer() {
    return new Uint8Array([0, 0]).buffer;
  };
}

const WORDS = [
  { word: "I'll", accuracy: 97, clean: true },
  { word: "grab", accuracy: 100, clean: true },
  { word: "the", accuracy: 62, clean: false },
];

function mockRecorder() {
  const stop = vi.fn();
  class FakeRecorder {
    static isTypeSupported = () => true;
    mimeType = "audio/webm;codecs=opus";
    ondataavailable: ((e: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    start() {
      this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2])]) });
    }
    stop() {
      stop();
      this.onstop?.();
    }
  }
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  vi.stubGlobal("navigator", {
    ...navigator,
    mediaDevices: { getUserMedia: vi.fn(async () => ({ getTracks: () => [] })) },
  });
  vi.stubGlobal(
    "AudioContext",
    class {
      sampleRate = 48000;
      async decodeAudioData() {
        return {
          numberOfChannels: 1,
          length: 4,
          sampleRate: 48000,
          getChannelData: () => new Float32Array([0, 0.5, -0.5, 0]),
        };
      }
      async close() {}
    },
  );
  return { stop };
}

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
    mockRecorder();
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
    expect(screen.getByRole("button")).toHaveTextContent(SHADOW.start);
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
    await user.click(screen.getByRole("button")); // start
    await user.click(screen.getByRole("button")); // stop

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
      await user.click(screen.getByRole("button"));
      await user.click(screen.getByRole("button"));
      await waitFor(() => expect(screen.getByTestId("shadow-result")).toBeTruthy());
      expect(screen.queryByText(SHADOW.improved) !== null).toBe(expected);
      view.unmount();
    }
  });

  it("says scoring is off on a 409 and does not read it as a bad attempt", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 409 })));
    const user = userEvent.setup();
    render(<ShadowLine cardId={1} sentence="A line to say." />);
    await user.click(screen.getByRole("button"));
    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByTestId("shadow-off")).toBeTruthy());
    expect(screen.getByTestId("shadow-off")).toHaveTextContent(
      SHADOW.unavailable,
    );
    expect(screen.queryByTestId("shadow-result")).toBeNull();
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
    await user.click(screen.getByRole("button"));
    await user.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByTestId("shadow-result")).toBeTruthy());

    // **The audio existed in memory for one request and nowhere else.**
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(setItem).not.toHaveBeenCalled();
    expect(indexedDBOpen).not.toHaveBeenCalled();
    expect(container.querySelectorAll("a[download]")).toHaveLength(0);
  });
});
