"use client";

import { readString } from "@/lib/items";

import { AudioButton } from "../audio-button";
import { Cue, Stem } from "./shared";
import type { PresentationProps } from "./types";

/**
 * Listen and type it back. `prompt_text` is the instruction; the sentence is
 * the answer and reaches the learner **only as audio** — never as text on the
 * wire, which is why `items.item_audio` synthesises inside the service and
 * hands the route bytes.
 */
export default function Dictation({ itemId, projection }: PresentationProps) {
  return (
    <div className="space-y-4">
      <Stem>{readString(projection, "prompt_text")}</Stem>
      <Cue text={readString(projection, "cue")} />
      <AudioButton itemId={itemId} />
    </div>
  );
}
