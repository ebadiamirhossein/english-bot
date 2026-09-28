"use client";

import { l1Attributes } from "@/components/l1-text";
import { readString } from "@/lib/items";

import { Cue, Instruction, Stem } from "./shared";
import type { PresentationProps } from "./types";

/**
 * Farsi in, English out — PRD §4's highest-value drill, and the one v2 lacked.
 *
 * `l1` in the projection is the **language tag** (`fa` / `lt`), not the text:
 * the sentence is `prompt_text`, which for this one type is not English. The
 * tag goes on `lang`, and `dir="auto"` lets the browser resolve direction from
 * the script — right for the Farsi learner and the Lithuanian one without this
 * file knowing which is looking.
 */
export default function L1ToL2Production({ projection }: PresentationProps) {
  const language = readString(projection, "l1") ?? undefined;
  // W32f (B3): a Farsi prompt is `dir="rtl"` and set in Vazirmatn (`font-l1`);
  // any other language keeps `dir="auto"` and the page's face, as before.
  const farsi = language ? l1Attributes(language) : null;
  return (
    <div className="space-y-4">
      <Instruction>Say this in English.</Instruction>
      <div dir={farsi?.dir === "rtl" ? "rtl" : "auto"} lang={language}>
        <Stem face={farsi?.face}>{readString(projection, "prompt_text")}</Stem>
      </div>
      <Cue text={readString(projection, "cue")} />
    </div>
  );
}
