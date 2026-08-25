"use client";

import { readString } from "@/lib/items";

import { AudioButton } from "../audio-button";
import { Cue, Instruction, Stem } from "./shared";
import type { PresentationProps } from "./types";

/**
 * The sentence on screen with one `___`, and the whole sentence in the ear.
 *
 * The transcript is not in the projection — it is the answer wearing a
 * different hat. It reaches the learner spoken, because that is the exercise.
 *
 * W5a gave this type both gates rather than one: the audio round-trip proved
 * the gapped word was *audible*, and nothing proved it was the only word that
 * *fits*, so it also goes through the blind solver.
 */
export default function ListeningGap({
  itemId,
  projection,
}: PresentationProps) {
  return (
    <div className="space-y-4">
      <Instruction>Listen, then fill the gap.</Instruction>
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />
      <AudioButton itemId={itemId} />
    </div>
  );
}
