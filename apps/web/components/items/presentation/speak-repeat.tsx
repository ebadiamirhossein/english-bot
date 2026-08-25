"use client";

import { readString } from "@/lib/items";

import { AudioButton } from "../audio-button";
import { Cue, Instruction, Stem } from "./shared";
import type { PresentationProps } from "./types";

/**
 * Read the sentence and say it. The answer *is* the prompt, so showing it is
 * the exercise rather than a leak.
 *
 * The audio is a model to copy, not a stimulus to decode — the sentence is
 * already on screen, so nothing is given away by playing it.
 */
export default function SpeakRepeat({
  itemId,
  projection,
}: PresentationProps) {
  return (
    <div className="space-y-4">
      <Instruction>Say this out loud.</Instruction>
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />
      <AudioButton itemId={itemId} />
    </div>
  );
}
