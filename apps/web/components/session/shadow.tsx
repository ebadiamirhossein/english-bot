"use client";

/**
 * Block 4's speak half. W14, PRD §8 rung 1.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * **NO RESAMPLE, AND THAT IS P0a's RESULT RATHER THAN A SIMPLIFICATION.**
 *
 * The plan (§1c) ruled that the browser must normalise to 16 kHz mono PCM,
 * because the two phones emit different containers (Safari mp4/AAC, Chrome
 * webm/Opus) and neither is natively accepted. **That ruling was made without
 * evidence, and the evidence removed most of it.** P0a sent the same utterance
 * at 48 kHz and at 16 kHz on 2026-09-03: **Azure accepted BOTH, with identical
 * scores** (accuracy 98.0, pron 98.8, 7 words, 23 phonemes in all three
 * recordings).
 *
 * So the resample is **dropped**: no `OfflineAudioContext`, no linear
 * interpolation, no box-average pre-filter, and **#362 — WebKit refusing
 * `OfflineAudioContext` at 16 kHz — closes on evidence rather than on a
 * workaround.** P0b was never run because it became unnecessary.
 *
 * **WHAT REMAINS IS CONTAINER NORMALISATION ONLY**: decode whatever the device
 * recorded, downmix to mono, and wrap the samples in a WAV header **at the
 * device's own sample rate**. `decodeAudioData` handles both containers, and
 * `AudioContext.sampleRate` is whatever the hardware gives us.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * **NOTHING IS WRITTEN ANYWHERE.** The recording lives as chunks in a local
 * array, becomes one `Blob`, is POSTed, and is dropped. No `createObjectURL`
 * save, no `<a download>`, no IndexedDB, no `localStorage`. The learner's audio
 * exists in memory for the length of one request, on the device and on the
 * server both (CLAUDE.md §5, PRD §8).
 *
 * **NO AGGREGATE SCORE IS RENDERED** (§2.6). The wire carries per-word accuracy
 * and nothing else; there is no accuracy/fluency/completeness/pron number in
 * the response model at all, so this component cannot show one it was never
 * given. **Raises are announced and drops are silent**: `improved === true`
 * says so, and `null` covers both *first attempt* and *worse* — this component
 * has no branch that can tell those apart, deliberately.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { API_BASE_URL } from "@/lib/env";
import { SHADOW } from "./copy";

/** A word below this reads as *worth another go*. Amber, never red. */
const NEEDS_WORK = 80;

type Word = { word: string; accuracy: number; clean: boolean };
type Scored = { attempt_id: number; words: Word[]; improved: boolean | null };

type Phase =
  | "idle"
  | "recording"
  | "scoring"
  | "done"
  | "unavailable"
  | "notHeard"
  | "trouble";

/**
 * Root-mean-square of one `getByteTimeDomainData` frame, as 0..1. **#367.**
 *
 * Byte time-domain data is centred on 128, so the deviation from 128 is the
 * signal. **Pure and exported so the meter is testable without a microphone** —
 * a level meter driven by a fixed animation would look identical on screen and
 * tell the learner nothing, which is the defect this fixes, so the test asserts
 * the number MOVES WITH REAL INPUT.
 *
 * Clamped to 1: a hot mic clips at 0/255 and must not overflow the bar.
 */
export function rmsFromTimeDomain(frame: Uint8Array): number {
  if (frame.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i += 1) {
    const deviation = (frame[i] - 128) / 128;
    sum += deviation * deviation;
  }
  return Math.min(1, Math.sqrt(sum / frame.length));
}

/** Interleaved channels → mono, then a 16-bit PCM WAV at the SOURCE rate. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const bytes = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(bytes);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) {
      view.setUint8(offset + i, text.charCodeAt(i));
    }
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, clamped * 0x7fff, true);
  }
  return new Blob([bytes], { type: "audio/wav" });
}

/** Average the channels. Mono in, mono out; stereo in, one track out. */
export function downmix(buffer: AudioBuffer): Float32Array {
  const channels = buffer.numberOfChannels;
  if (channels === 1) return buffer.getChannelData(0);
  const out = new Float32Array(buffer.length);
  for (let c = 0; c < channels; c += 1) {
    const data = buffer.getChannelData(c);
    for (let i = 0; i < data.length; i += 1) out[i] += data[i] / channels;
  }
  return out;
}

export function ShadowLine({
  cardId,
  sentence,
  sessionId,
}: {
  cardId: number;
  sentence: string;
  sessionId?: number;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [scored, setScored] = useState<Scored | null>(null);
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

  const stopTracks = useCallback(() => {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }, []);

  /**
   * **Tear the meter down on every exit path.** An interval left running would
   * keep reading the microphone after the learner stopped — which is the one
   * thing a recording indicator must never do, since its whole job is to be
   * truthful about whether the mic is live.
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

  useEffect(() => stopMeter, [stopMeter]);

  const send = useCallback(
    async (recorded: Blob) => {
      setPhase("scoring");
      try {
        // **Container normalisation only — no resample (P0a).** `decodeAudioData`
        // accepts Safari's mp4/AAC and Chrome's webm/Opus alike, and the WAV
        // goes out at whatever rate the hardware used.
        const context = new AudioContext();
        const decoded = await context.decodeAudioData(
          await recorded.arrayBuffer(),
        );
        const wav = encodeWav(downmix(decoded), decoded.sampleRate);
        await context.close();

        const query = sessionId ? `?session_id=${sessionId}` : "";
        const response = await fetch(
          `${API_BASE_URL}/shadow/${cardId}/score${query}`,
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "audio/wav" },
            body: wav,
          },
        );
        if (response.status === 409) {
          // Quota. **A stated condition, never an error face.**
          setPhase("unavailable");
          return;
        }
        if (response.status === 422) {
          // **#366: the request completed and the app heard NOTHING.**
          // Distinct from `trouble` (a request that did not complete) because
          // the learner should know which happened, and distinct from a result
          // because there is no result -- rendering colouring here would be a
          // verdict on an utterance nobody heard.
          setPhase("notHeard");
          return;
        }
        if (!response.ok) {
          setPhase("trouble");
          return;
        }
        setScored((await response.json()) as Scored);
        setPhase("done");
      } catch {
        setPhase("trouble");
      }
    },
    [cardId, sessionId],
  );

  const start = useCallback(async () => {
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = media;
      chunks.current = [];
      const rec = new MediaRecorder(media);
      rec.ondataavailable = (event) => chunks.current.push(event.data);
      rec.onstop = () => {
        stopMeter();
        stopTracks();
        void send(new Blob(chunks.current, { type: rec.mimeType }));
        chunks.current = [];
      };
      recorder.current = rec;

      // **THE METER READS THE REAL SIGNAL.** `AnalyserNode` is Web Audio --
      // the same API `decodeAudioData` already comes from -- so **no new
      // dependency**. A 50 ms interval (20 fps) rather than
      // `requestAnimationFrame`: it is smooth enough for a level bar, it stops
      // deterministically, and it is testable with fake timers, where rAF in
      // jsdom is not.
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
      setPhase("recording");
    } catch {
      setPhase("trouble");
    }
  }, [send, stopTracks, stopMeter]);

  const stop = useCallback(() => {
    recorder.current?.stop();
    recorder.current = null;
  }, []);

  return (
    <div className="space-y-3" data-testid="shadow">
      <p className="text-sm text-muted-foreground">{SHADOW.prompt}</p>

      {phase === "done" && scored ? (
        <p className="text-lg leading-relaxed" data-testid="shadow-result">
          {scored.words.map((w, i) => {
            const weak = !w.clean || w.accuracy < NEEDS_WORK;
            return (
              <span
                key={`${w.word}-${i}`}
                data-weak={weak ? "true" : "false"}
                className={
                  weak
                    ? // **Amber and an underline, never red and never a mark.**
                      // `❌` and `✗` are banned outright, and colour is never
                      // the only signal — the underline carries it too.
                      "text-amber-600 underline decoration-2 underline-offset-4 dark:text-amber-500"
                    : "text-foreground"
                }
              >
                {w.word}
                {i < scored.words.length - 1 ? " " : ""}
              </span>
            );
          })}
        </p>
      ) : (
        <p className="text-lg leading-relaxed" data-testid="shadow-sentence">
          {sentence}
        </p>
      )}

      {/* Raises announced. A drop renders nothing at all. */}
      {phase === "done" && scored?.improved === true ? (
        <p className="text-sm text-muted-foreground">{SHADOW.improved}</p>
      ) : null}

      {/* **#367: EVIDENCE THAT THE MICROPHONE IS LIVE.**

          Before this, *Say it* became *Done* with nothing between, and the
          database showed what that cost: 11.90 s and 7.61 s captured for a ~5 s
          sentence, with completeness BELOW accuracy on both — dead air, because
          the learner could not tell when recording started or stopped.

          The bar is driven by `rmsFromTimeDomain` over real input, so **it is
          still when the room is still**, which is the only way it can be
          trusted as an indicator. */}
      {phase === "recording" ? (
        <div className="space-y-2">
          <div
            className="flex items-center gap-3"
            role="status"
            aria-live="off"
            aria-label={SHADOW.listening}
          >
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                data-testid="shadow-level"
                data-level={level.toFixed(3)}
                className="h-full rounded-full bg-foreground/70 transition-[width] duration-75"
                style={{ width: `${Math.round(level * 100)}%` }}
              />
            </div>
            <span
              data-testid="shadow-elapsed"
              className="w-10 shrink-0 text-right font-mono text-sm tabular-nums text-muted-foreground"
            >
              {elapsed}s
            </span>
          </div>
          <p className="text-sm text-muted-foreground">{SHADOW.listening}</p>
        </div>
      ) : null}

      {phase === "notHeard" ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid="shadow-not-heard"
        >
          {SHADOW.notHeard}
        </p>
      ) : null}

      {phase === "unavailable" ? (
        <p className="text-sm text-muted-foreground" data-testid="shadow-off">
          {SHADOW.unavailable}
        </p>
      ) : null}
      {phase === "trouble" ? (
        <p className="text-sm text-muted-foreground" data-testid="shadow-trouble">
          {SHADOW.trouble}
        </p>
      ) : null}

      {phase === "scoring" ? (
        <p className="text-sm text-muted-foreground" data-testid="shadow-wait">
          {SHADOW.waiting}
        </p>
      ) : (
        <Button
          type="button"
          size="lg"
          variant={phase === "recording" ? "default" : "outline"}
          onClick={phase === "recording" ? stop : start}
          className="h-14 w-full rounded-2xl text-base font-semibold"
        >
          {phase === "recording"
            ? SHADOW.stop
            : phase === "done" || phase === "notHeard"
              ? SHADOW.again
              : SHADOW.start}
        </Button>
      )}
    </div>
  );
}
