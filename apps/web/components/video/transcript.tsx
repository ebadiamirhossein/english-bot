"use client";

/**
 * The transcript, as **unsynced, word-clickable text**. W13-i.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * **IT IS SYNCED AS OF THE CUE-TIMINGS SLICE, AND THE OLD NOTE IS QUOTED RATHER
 * THAN DELETED (#82's shape):** *"WHY THIS IS NOT SYNCED TO THE PLAYER, AND IT
 * IS A DATA FACT RATHER THAN A DECISION (R12)."* **T5 recovered the timings
 * from `--dump` files at no charge**, migration 021 stores them, and the
 * follow-along highlight is built below. **Loop-a-line and per-line 0.75x are
 * NOT, and they are not held either — they are reported UNMET**, because a
 * generated track is a rolling window and has no line boundaries: ~92% of
 * consecutive pairs overlap on every generated track measured, and all three
 * assigned videos are generated. The original finding stands as written:**
 *
 * There are **no per-cue timings anywhere in this database.** `videos.transcript`
 * is a single `TEXT` column; `core/video_api.py`'s `_read_text` returns the first
 * non-empty of the adapter's `text_keys`, and for the ruled actor those are
 * `("non_timestamped", "transcript", "text")` — **`non_timestamped` first,
 * deliberately** — while the list fallback joins each segment's `text` and
 * **discards every `start`**. `refresh.py` writes that one flattened string.
 *
 * So the follow-along highlight, **loop-a-line** and **per-line 0.75×** have no
 * data behind them and are **held, not dropped**. They return under §2g(b)'s
 * option A or B, both of which take migration `021` — #185's eighth occurrence —
 * and **T5 decides which**. Reported rather than worked around, and reported
 * once: the card-timestamp half of the same finding is W13-ii's, not this file's.
 *
 * **What IS built here, and needs no timings:** every word is tappable, and the
 * words this learner has no `known`/`mastered` ledger row for are marked.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * **THE TAP DOES NOT DEFINE ANYTHING YET, AND THAT IS THE OPERATOR'S RULING TO
 * MAKE (§1a).** Tap-to-define and Add-to-deck are **W13-ii** and reach a model;
 * the standing ruling of 2026-08-27 is that the app never generates while a
 * learner waits and never while nobody is watching, and all three of W13's
 * generating surfaces are on-demand generation with a person watching. **Until
 * that is ruled, a tap selects the word and does nothing else** — a surface that
 * silently spent money on a tap would be the thing the ruling forbids.
 */

import { useMemo } from "react";

/**
 * **THE RULING: the active cue is the one with the greatest `start` at or before
 * `t`.** This function never reads `duration`, and that is the argument rather
 * than an optimisation — it makes the selection **total** (one answer, never
 * two, however many windows are live) and **monotone** (the highlight advances
 * and cannot jump backwards). The ~92% overlap lives entirely in `duration`, so
 * it cannot reach this rule.
 *
 * **This is the TypeScript half of a rule whose definition lives in
 * `packages/core/video/cues.py::active_cue`**, where the declined alternatives
 * and the three boundaries are recorded. The two must agree; the Python tests
 * hold the definition.
 */
function activeCueIndex(cues: Cue[], positionS: number): number | null {
  let found: number | null = null;
  for (let i = 0; i < cues.length; i += 1) {
    if (cues[i].start <= positionS) found = i;
    else break;
  }
  return found;
}

/** One cue as migration 021 stores it. `duration` is carried and read by
 * nothing — see `activeCueIndex`. */
export type Cue = { text: string; start: number; duration?: number };

/** Highlighting is per WORD, so the split has to keep what it splits on. */
const TOKEN = /([A-Za-zÀ-ɏ']+)/g;

/**
 * Lowercased, apostrophes kept.
 *
 * **This is NOT lemmatisation and must not become it.** `unknown_lemmas` arrives
 * from `core.lexicon`, which lemmatises with the seed list and the inflection
 * table; a second, cruder normaliser in TypeScript would be a **second
 * instrument on one screen** — the pair that agrees until it doesn't. So an
 * inflected form whose lemma is unknown is simply not marked here, which errs
 * toward marking too little. **Marking too little is the safe direction**: a
 * missed highlight is a word the learner reads normally, while a wrong one
 * tells them they do not know something they do.
 */
function surfaceKey(word: string): string {
  return word.toLowerCase();
}

export function Transcript({
  text,
  unknownLemmas,
  language,
  cues,
  positionS,
  onWordTap,
}: {
  text: string;
  unknownLemmas: string[];
  language: string;
  /** **Absent means the third state**: transcript present, cues absent. It
   * renders, words stay tappable, the badge still shows, and **nothing is said
   * to the learner** about a highlight they have not seen. */
  cues?: Cue[];
  positionS?: number;
  onWordTap?: (word: string) => void;
}) {
  const unknown = useMemo(
    () => new Set(unknownLemmas.map(surfaceKey)),
    [unknownLemmas],
  );

  const parts = useMemo(() => text.split(TOKEN), [text]);

  /**
   * The active cue's `[start, end)` character range in `text`.
   *
   * **Exact, and exact only because the join reproduces the stored transcript
   * byte for byte** — the three-way md5 T5 measured, and the gate
   * `core.video.cues.reproduces` enforces on every write. Without that identity
   * these offsets would be a guess against a re-tokenisation, which is the
   * second instrument this design refuses.
   */
  const span = useMemo<[number, number] | null>(() => {
    if (!cues?.length || positionS === undefined) return null;
    const index = activeCueIndex(cues, positionS);
    if (index === null) return null;
    let cursor = 0;
    for (let i = 0; i < index; i += 1) cursor += cues[i].text.length + 1;
    return [cursor, cursor + cues[index].text.length];
  }, [cues, positionS]);

  return (
    <p
      lang={language}
      className="max-w-prose text-base leading-loose"
      data-testid="transcript"
    >
      {(() => {
        let offset = 0;
        return parts.map((part, index) => {
        const at = offset;
        offset += part.length;
        // Inside the active cue's character range. `data-testid` marks the
        // FIRST such part so a test can read the lit cue's text back.
        const lit =
          span !== null && at >= span[0] && at + part.length <= span[1];
        if (!TOKEN.test(part)) {
          TOKEN.lastIndex = 0;
          return (
            <span key={index} data-lit={lit ? "true" : undefined}>
              {part}
            </span>
          );
        }
        TOKEN.lastIndex = 0;
        const isUnknown = unknown.has(surfaceKey(part));
        return (
          <button
            key={index}
            type="button"
            // **`data-unknown` and not a colour name.** The palette owns how an
            // unknown word looks; a component that named a colour would put the
            // theme in two places.
            data-unknown={isUnknown ? "true" : undefined}
            data-lit={lit ? "true" : undefined}
            data-testid={isUnknown ? "unknown-word" : "known-word"}
            onClick={onWordTap ? () => onWordTap(part) : undefined}
            className={
              "rounded-sm px-px transition-colors " +
              (isUnknown
                ? "bg-accent/60 underline decoration-dotted underline-offset-4"
                : "hover:bg-muted")
            }
          >
            {part}
          </button>
        );
        });
      })()}
      {span !== null ? (
        // The lit cue's text, for assertion and for assistive technology. Not
        // a second rendering of the transcript — one element, aria-hidden from
        // the reading order, carrying what the highlight currently covers.
        <span className="sr-only" data-testid="cue-active">
          {text.slice(span[0], span[1])}
        </span>
      ) : null}
    </p>
  );
}
