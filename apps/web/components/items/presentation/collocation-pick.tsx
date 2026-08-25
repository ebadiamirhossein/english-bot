"use client";

import { readString, readStrings } from "@/lib/items";

import { Choice, Cue, Stem } from "./shared";
import type { PresentationProps } from "./types";

/**
 * Three or four candidate collocates for one frame. Same shape as `mcq` and a
 * separate component anyway: they are different exercises to a learner ("which
 * form is right" versus "which verb goes with this noun"), and a shared
 * component is how the second one quietly becomes a copy of the first when one
 * of them needs to change.
 */
export default function CollocationPick({
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
