"use client";

import { Button } from "@/components/ui/button";
import { isAnswered } from "@/lib/items";

import type { AnswerProps } from "./types";

/**
 * The typed input, for `cloze_cued`, `l1_to_l2_production`, `dictation` and
 * `listening_gap` — chosen by response mode, so this file names none of them.
 *
 * **The four attributes below are not cosmetic; the phone keyboard is a second
 * grader.** Autocorrect silently repairing a learner's spelling before it is
 * graded is a teaching bug: the acceptance criterion "typed items never require
 * punctuation or capitalisation to match" is about `fold_answer` being
 * permissive on the server, not about iOS fixing the answer first. And
 * `text-base` is 16px on purpose — below that, Safari zooms the viewport on
 * focus, which is a layout shift mid-sentence.
 *
 * Whether iOS actually honours `autoCorrect="off"` for this input is an
 * empirical question about a real device; jsdom has no autocorrect, so the test
 * here asserts the attributes and the human check on a phone settles the rest.
 *
 * There is no comparison of any kind in this file. There is nothing to compare
 * against: the projection carries no answer.
 */
export default function TypedAnswer({
  draft,
  onDraft,
  onSubmit,
  submitting,
  answered,
}: AnswerProps) {
  const value = draft.text ?? "";
  const ready = isAnswered({ text: value });

  return (
    <form
      className="space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (ready && !submitting && !answered) onSubmit({ text: value });
      }}
    >
      <input
        type="text"
        value={value}
        disabled={answered}
        onChange={(event) => onDraft({ text: event.target.value })}
        placeholder="Type your answer"
        aria-label="Your answer"
        autoCapitalize="off"
        autoCorrect="off"
        autoComplete="off"
        spellCheck={false}
        inputMode="text"
        enterKeyHint="done"
        data-testid="typed-answer-input"
        className="h-14 w-full rounded-2xl border border-border bg-card px-4 text-base outline-none transition-colors placeholder:text-muted-foreground/70 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60"
      />
      {answered ? null : (
        <Button
          type="submit"
          size="lg"
          disabled={!ready || submitting}
          className="h-14 w-full rounded-2xl text-base font-semibold"
        >
          {submitting ? "Checking…" : "Check"}
        </Button>
      )}
    </form>
  );
}
