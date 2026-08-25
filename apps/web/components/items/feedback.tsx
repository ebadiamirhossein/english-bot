"use client";

import type { ItemAnswerResult } from "@/lib/api";

/**
 * **The one moment in the app where a learner finds out how they did.**
 *
 * W6 shipped this as a flat tinted rectangle with a line of text in it,
 * indistinguishable in weight from the tiles above it. The human ran all six
 * seeded items on a phone and named it as the weakest thing in the slice, which
 * it was: the screen that answers *how did I do* has to be legible at a glance,
 * before a word is read.
 *
 * **The outcome is carried by weight, fill and structure — never by colour
 * alone.** The palette has no red in it by design (`apps/web/README.md`), so
 * colour could not carry it even if that were a good idea, and a treatment that
 * depends on hue fails anyone who cannot separate the two.
 *
 *   correct → a **filled** panel, one short line, set large. Nothing to study.
 *   wrong   → an **outlined** panel with a rule down its edge, and the answer
 *             set at display size as the thing the box is built around.
 *   self    → an outlined panel, quieter than either, with no verdict at all.
 *
 * So the shapes differ (filled vs outlined), the density differs (one line vs
 * two tiers), and the emphasis differs — three signals before the text.
 *
 * **Three rules that are CLAUDE.md §4 rather than taste:**
 *
 *  - Nothing red, no ✗, nothing struck through. A miss is information, not an
 *    alarm, and wrong is *quieter* than right rather than louder.
 *  - The emphasis goes on the better version, never on what was submitted. What
 *    you got wrong is not the part worth reading twice.
 *  - No verdict word passes judgement on the person. The banned-phrase scan over
 *    every `.tsx` fails this file for "wrong", "incorrect", "missed" or
 *    "failed" — the obvious phrasings are exactly the ones to refuse.
 */
/**
 * Shared box geometry — and `min-h-20` is load-bearing, not spacing.
 *
 * The "Check" button is `h-14` (56px) and vanishes the moment an answer is
 * graded; this box takes its place and **Next renders below it**. A short box
 * would let Next land under the thumb that just tapped Check, so a second tap
 * of an eager finger would skip past the feedback entirely — worse than showing
 * no box at all. 80px guarantees Next is displaced clear of the last touch
 * point whatever the verdict's content. The real check is a person on a phone.
 */
const BOX = "min-h-20 rounded-2xl px-5 py-5";

export function Feedback({ result }: { result: ItemAnswerResult }) {
  // **#113 — a self-mark is not a verdict, and this branch comes first.**
  //
  // W6 rendered `👍 That's it.` when the learner tapped "Got it" on
  // `speak_answer` — the same confirmation a graded answer gets, for an answer
  // nothing checked. No microphone is opened in W6 and no audio exists, so the
  // app was asserting a correctness it does not have. `graded_by` exists
  // precisely so instruments are never silently mixed; rendering them
  // identically mixes them where it matters most, in front of the learner.
  //
  // "Noted." records what happened without confirming it. **No thumb** — the
  // thumb is a verdict and there is no verdict here.
  if (result.graded_by === "self") {
    return (
      <div
        className={`${BOX} border border-border border-l-4 border-l-muted-foreground/30 bg-card space-y-1`}
        data-testid="feedback"
        data-correct={String(result.correct)}
        data-graded-by="self"
      >
        <p className="font-heading text-xl leading-snug">Noted.</p>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Pronunciation scoring comes later.
        </p>
      </div>
    );
  }

  if (result.correct) {
    return (
      <div
        className={`${BOX} flex items-center gap-3 bg-accent text-accent-foreground`}
        data-testid="feedback"
        data-correct="true"
        data-graded-by={result.graded_by}
      >
        <span aria-hidden className="text-2xl leading-none">
          👍
        </span>
        <p className="font-heading text-xl leading-snug">That&rsquo;s it.</p>
      </div>
    );
  }

  // **#112 — the lead-in never promises something the box cannot show.**
  //
  // Reproduced on production 2026-08-25: pairing `match_pairs` wrong rendered
  // "Not quite. Here it is:" followed by nothing. `match_pairs` has
  // `answer IS NULL` by schema rule — its correct answer is a mapping, not a
  // string — so `canonical` is empty and the lead-in was writing a cheque the
  // box could not cash. Telling a learner the answer is coming and then not
  // showing it is worse than not offering, because they wait for it.
  //
  // **W7 supplies the missing half (#118).** The answer route now returns the
  // correct pairing after grading, with exactly `canonical`'s standing — so the
  // box can show it, and `match_pairs` stops being the one type where getting
  // it wrong taught nothing.
  const pairs = result.pairs ?? null;
  const showsAnswer = Boolean(result.canonical) || Boolean(pairs?.length);

  return (
    <div
      className={`${BOX} border border-border border-l-4 border-l-primary bg-card`}
      data-testid="feedback"
      data-correct="false"
      data-graded-by={result.graded_by}
      data-shows-answer={String(showsAnswer)}
    >
      <p className="text-sm leading-relaxed text-muted-foreground">
        {showsAnswer ? "Not quite. Here it is:" : "Not quite."}
      </p>
      {result.canonical ? (
        // The reason the box exists. Set at display size because it is what the
        // learner is here to read — the box is built around it rather than
        // beside it.
        <p
          className="mt-1.5 font-heading text-2xl leading-snug text-primary"
          data-testid="feedback-canonical"
        >
          {result.canonical}
        </p>
      ) : null}
      {pairs?.length ? (
        // A bijection is not a sentence, so it is not set as one. Each row is
        // the pair as a pair; reading it back is the whole lesson, and a
        // comma-joined string would make the learner re-parse what they just
        // got wrong.
        <ul className="mt-1.5 space-y-1" data-testid="feedback-pairs">
          {pairs.map(([left, right]) => (
            <li
              key={`${left}\u0000${right}`}
              className="font-heading text-lg leading-snug text-primary"
            >
              {left} <span aria-hidden className="opacity-50">→</span> {right}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
