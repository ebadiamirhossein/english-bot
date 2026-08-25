"use client";

import { readString } from "@/lib/items";

import { Cue, Stem } from "./shared";
import type { PresentationProps } from "./types";

/**
 * A sentence with one `___`. The gap lives inside `prompt_text` and there is no
 * separate field, because two representations of one gap is how they disagree.
 *
 * The typed input is the answer component's, not this one's.
 */
export default function ClozeCued({ projection }: PresentationProps) {
  return (
    <div className="space-y-4">
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />
    </div>
  );
}
