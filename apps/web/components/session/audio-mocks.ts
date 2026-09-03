/**
 * The fake microphone stack, in ONE place. W14.
 *
 * **Two test files drive `ShadowLine` and both need the same audio globals.**
 * When `recorder.test.tsx` added `createAnalyser` for the level meter (#367),
 * `shadow.test.tsx`'s older copy did not have it, `start()` threw, and five
 * tests failed for a reason that had nothing to do with what they assert —
 * **two producers of one contract, which is #190's shape arriving in the test
 * suite instead of the app.** One definition, imported by both.
 *
 * `amplitude` is module state on purpose: the meter test needs to change what
 * the microphone "hears" between assertions, and a level meter that cannot be
 * driven from the test is a level meter whose movement proves nothing.
 */

import { vi } from "vitest";

/** What the fake analyser reports, in 0–127 units either side of 128. */
export const mic = { amplitude: 0 };

export function mockAudio(): void {
  mic.amplitude = 0;

  class FakeRecorder {
    static isTypeSupported = () => true;
    mimeType = "audio/webm;codecs=opus";
    ondataavailable: ((e: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    start() {
      this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2])]) });
    }
    stop() {
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
      createMediaStreamSource() {
        return { connect: vi.fn(), disconnect: vi.fn() };
      }
      createAnalyser() {
        return {
          fftSize: 2048,
          frequencyBinCount: 1024,
          connect: vi.fn(),
          disconnect: vi.fn(),
          getByteTimeDomainData: (buf: Uint8Array) => {
            for (let i = 0; i < buf.length; i += 1) {
              buf[i] = 128 + (i % 2 === 0 ? mic.amplitude : -mic.amplitude);
            }
          },
        };
      }
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
}

/** jsdom has no `Blob.arrayBuffer()`; Safari 14+ and Chrome 76+ do. */
export function polyfillBlobArrayBuffer(): void {
  if (typeof Blob.prototype.arrayBuffer !== "function") {
    Blob.prototype.arrayBuffer = async function arrayBuffer() {
      return new Uint8Array([0, 0]).buffer;
    };
  }
}
