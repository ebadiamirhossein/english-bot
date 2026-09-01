"use client";

/**
 * The transcript, as **unsynced, word-clickable text**. W13-i.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * **WHY THIS IS NOT SYNCED TO THE PLAYER, AND IT IS A DATA FACT RATHER THAN A
 * DECISION (R12).**
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
  onWordTap,
}: {
  text: string;
  unknownLemmas: string[];
  language: string;
  onWordTap?: (word: string) => void;
}) {
  const unknown = useMemo(
    () => new Set(unknownLemmas.map(surfaceKey)),
    [unknownLemmas],
  );

  const parts = useMemo(() => text.split(TOKEN), [text]);

  return (
    <p
      lang={language}
      className="max-w-prose text-base leading-loose"
      data-testid="transcript"
    >
      {parts.map((part, index) => {
        if (!TOKEN.test(part)) {
          TOKEN.lastIndex = 0;
          return <span key={index}>{part}</span>;
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
      })}
    </p>
  );
}
