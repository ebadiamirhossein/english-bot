"use client";

import { readString } from "@/lib/items";

import { Cue, Instruction, Stem } from "./shared";
import type { PresentationProps } from "./types";

/**
 * Open production against a question. The rubric — what a good answer must
 * contain — is internal and never projected; it is what makes PRD §4.3's third
 * gate verifiable for a type with no canonical answer at all.
 *
 * No audio button: there is nothing to listen to, only something to say.
 */
export default function SpeakAnswer({ projection }: PresentationProps) {
  return (
    <div className="space-y-4">
      <Instruction>Answer out loud.</Instruction>
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />
    </div>
  );
}
