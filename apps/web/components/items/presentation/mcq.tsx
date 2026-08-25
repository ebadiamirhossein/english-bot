"use client";

import { readString, readStrings } from "@/lib/items";

import { Choice, Cue, Stem } from "./shared";
import type { PresentationProps } from "./types";

/**
 * Four options, one of which is the answer.
 *
 * This is the only shape where the answer being on screen is correct rather
 * than a leak: the task is *selecting* it, not recalling it, and a projection
 * that hid it would be unanswerable. What stays hidden is which one — and it
 * does, because the projection carries no marker and the options arrive in the
 * order the generator wrote them.
 */
export default function MCQ({
  projection,
  draft,
  onDraft,
  disabled,
}: PresentationProps) {
  const options = readStrings(projection, "options");
  return (
    <div className="space-y-4">
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />
      <div className="space-y-2">
        {options.map((option) => (
          <Choice
            key={option}
            label={option}
            selected={draft.option === option}
            disabled={disabled}
            onSelect={() => onDraft({ option })}
          />
        ))}
      </div>
    </div>
  );
}
