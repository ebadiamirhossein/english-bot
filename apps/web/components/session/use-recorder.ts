"use client";

/**
 * **ONE RECORDER, TWO SURFACES.** W13b/3 §C.
 *
 * `ShadowLine` built this in W14 and proved it: `MediaRecorder`, a level meter
 * driven by real input amplitude through `AnalyserNode`, an elapsed counter,
 * and teardown on every exit path including unmount. The conversation's
 * microphone needs exactly the same machinery.
 *
 * **SO IT IS EXTRACTED RATHER THAN COPIED — #190's rule: one contract, one
 * producer.** Two call sites assembling one shape, one of them incomplete and
 * both suites green because the halves never meet, is the defect that row
 * exists to describe. A second recorder would have been that, and the slice
 * prompt forbids it outright.
 *
 * **THE REFACTOR IS SAFE BECAUSE THE SHADOW SUITE IS WHAT PROVES IT.**
 * `shadow.test.tsx` and `recorder.test.tsx` exercise this machinery through
 * `ShadowLine`, and they were run before and after the extraction with no
 * change to their assertions. **The shadow surface is retired from the session
 * (2026-09-05, #390) and its code is deliberately alive for W17** — this hook
 * is now part of why that matters.
 *
 * **WHAT THIS HOOK DOES NOT DO, DELIBERATELY: it does not send anything.** It
 * hands back a `Blob` and the caller decides where it goes. Shadow posts WAV to
 * `/shadow/{id}/score`; the conversation posts to `/conversation/turn/voice`.
 * Putting the upload in here would make one function answer two contracts,
 * which is the thing it was extracted to avoid.
 *
 * **THE AUDIO RULES ARE THE CALLER'S AND ARE UNCHANGED:** no resample (P0a
 * established both providers take the native rate), the body cap is enforced
 * server-side before the body is read, nothing touches disk, and the transcript
 * is discarded after use.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { rmsFromTimeDomain } from "./shadow";

export type RecorderState = {
  /** True while the microphone is live. */
  recording: boolean;
  /** 0..1, from the real signal. Never a simulated animation. */
  level: number;
  /** Whole seconds since the recording started. */
  elapsed: number;
  start: () => Promise<void>;
  stop: () => void;
  /** True when `getUserMedia` refused — permission, or no device.
   *
   * **NAMED `unavailable` AND NOT `failed`, AND THAT IS NOT COSMETIC.**
   * `test_no_guilt_copy_anywhere_in_the_frontend` is blunt on purpose and
   * fires on a VARIABLE called `failed`; its own docstring says to rename the
   * variable, because *a scan that tries to tell copy from code is a scan that
   * misses copy.* It caught this one. `unavailable` is also the shadow
   * surface's existing word for the same shape. */
  unavailable: boolean;
};

export function useRecorder(onRecorded: (blob: Blob) => void): RecorderState {
  const [recording, setRecording] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<BlobPart[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const meter = useRef<{
    context: AudioContext;
    analyser: AnalyserNode;
    timer: ReturnType<typeof setInterval>;
  } | null>(null);
  // The callback is held in a ref so `start` does not change identity when the
  // caller re-renders — a recorder that restarts on every parent render would
  // drop audio mid-sentence.
  const sink = useRef(onRecorded);
  sink.current = onRecorded;

  const stopTracks = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);

  /**
   * **Tear the meter down on every exit path.** An interval left running would
   * keep reading the microphone after the learner stopped — the one thing a
   * recording indicator must never do, since its whole job is to be truthful
   * about whether the mic is live.
   */
  const stopMeter = useCallback(() => {
    if (!meter.current) return;
    clearInterval(meter.current.timer);
    meter.current.analyser.disconnect();
    void meter.current.context.close();
    meter.current = null;
    setLevel(0);
    setElapsed(0);
  }, []);

  // Unmount is an exit path too — navigating away mid-recording must release
  // the microphone.
  useEffect(
    () => () => {
      stopMeter();
      stopTracks();
      recorder.current = null;
    },
    [stopMeter, stopTracks],
  );

  const start = useCallback(async () => {
    setUnavailable(false);
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = media;
      chunks.current = [];
      const rec = new MediaRecorder(media);
      rec.ondataavailable = (event) => chunks.current.push(event.data);
      rec.onstop = () => {
        stopMeter();
        stopTracks();
        setRecording(false);
        sink.current(new Blob(chunks.current, { type: rec.mimeType }));
        chunks.current = [];
      };
      recorder.current = rec;

      // **THE METER READS THE REAL SIGNAL.** `AnalyserNode` is Web Audio, the
      // same API `decodeAudioData` already comes from, so no new dependency. A
      // 50 ms interval rather than `requestAnimationFrame`: smooth enough for a
      // level bar, it stops deterministically, and it is testable with fake
      // timers where rAF in jsdom is not.
      const context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      context.createMediaStreamSource(media).connect(analyser);
      const frame = new Uint8Array(analyser.fftSize);
      const startedAt = Date.now();
      const timer = setInterval(() => {
        analyser.getByteTimeDomainData(frame);
        setLevel(rmsFromTimeDomain(frame));
        setElapsed(Math.floor((Date.now() - startedAt) / 1000));
      }, 50);
      meter.current = { context, analyser, timer };

      rec.start();
      setRecording(true);
    } catch {
      setUnavailable(true);
      setRecording(false);
    }
  }, [stopMeter, stopTracks]);

  const stop = useCallback(() => {
    recorder.current?.stop();
    recorder.current = null;
  }, []);

  return { recording, level, elapsed, start, stop, unavailable };
}
