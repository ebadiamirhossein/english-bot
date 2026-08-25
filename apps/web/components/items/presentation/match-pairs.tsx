"use client";

import { readString, readStrings } from "@/lib/items";

import { Cue, Instruction, Stem, Tile } from "./shared";
import type { PresentationProps } from "./types";

/**
 * Two independently sorted columns and a bijection to rebuild.
 *
 * The columns are sorted rather than shuffled — a random shuffle would make the
 * blind-solver gate non-reproducible, and sorting destroys the pairing just as
 * thoroughly, which is all that is needed. The mapping itself is never
 * projected: it is the answer.
 *
 * Tap a left word, then tap its meaning. Two taps rather than a drag, for the
 * same reason `word_bank_order` is tap-to-build.
 */
export default function MatchPairs({
  projection,
  draft,
  onDraft,
  disabled,
  result,
}: PresentationProps) {
  const left = readStrings(projection, "left");
  const right = readStrings(projection, "right");
  const pairs = draft.pairs ?? {};
  const pending = draft.option ?? "";
  const takenRights = new Set(Object.values(pairs));

  function pickLeft(word: string) {
    if (pairs[word]) {
      // Undo: drop just this pairing, keep the rest.
      const rest = Object.fromEntries(
        Object.entries(pairs).filter(([key]) => key !== word),
      );
      onDraft({ pairs: rest, option: "" });
      return;
    }
    onDraft({ pairs, option: pending === word ? "" : word });
  }

  function pickRight(meaning: string) {
    if (!pending) return;
    onDraft({ pairs: { ...pairs, [pending]: meaning }, option: "" });
  }

  return (
    <div className="space-y-4">
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />
      <Instruction>
        Tap a word, then tap its meaning. Tap a joined word to undo it.
      </Instruction>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-2" data-testid="match-left">
          {left.map((word) => (
            <Tile
              key={word}
              label={pairs[word] ? `${word} → ${pairs[word]}` : word}
              selected={pending === word || Boolean(pairs[word])}
              disabled={disabled}
              onSelect={() => pickLeft(word)}
            />
          ))}
        </div>
        <div className="flex flex-col gap-2" data-testid="match-right">
          {right.map((meaning) => (
            <Tile
              key={meaning}
              label={meaning}
              selected={takenRights.has(meaning)}
              disabled={disabled || takenRights.has(meaning) || !pending}
              onSelect={() => pickRight(meaning)}
            />
          ))}
        </div>
      </div>

      {/*
        **#118 — this type cannot show its correct answer yet, and says so.**

        `match_pairs` has `answer IS NULL` by schema rule: its correct answer is
        a bijection living in `items.payload.pairs`, which `visible_projection`
        withholds because it *is* the answer. Nothing on the client has it, and
        `AnswerOutcome` carries no field for it — the answer route returns
        `canonical` and nothing else. Supplying it would be an API change, which
        this closeout is explicitly barred from making.

        The copy promises nothing either — an earlier draft said the pairing
        "comes back on the next round", which is a second thing the app cannot
        currently deliver: item re-delivery under spacing is W7's.

        So the honest thing is to stop pretending. The verdict box no longer
        promises an answer it cannot produce (#112), and this says what a
        learner can actually do about it. #118 carries the real fix: the answer
        route returning the pairing **after grading**, which is not a projection
        leak for the same reason `canonical` is not.
      */}
      {result && !result.correct ? (
        <p
          className="text-sm leading-relaxed text-muted-foreground"
          data-testid="match-pairs-no-answer"
        >
          Worth another look at these two columns.
        </p>
      ) : null}
    </div>
  );
}
