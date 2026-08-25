/**
 * **The one file that maps a response mode to an input.** Three entries, and
 * three is the whole point: `core.items.RESPONSE_MODE` exists so that adding a
 * twelfth item type never adds a twelfth way to answer.
 *
 * `response_mode` arrives on the wire from `ItemPresentation`, so this app
 * holds no copy of that table. Nothing here names an item type, and
 * `tests/test_web_shell.py::test_only_the_presentation_map_branches_on_item_type`
 * fails the commit that changes it.
 */

import type { ComponentType } from "react";

import SpokenAnswer from "./spoken-answer";
import TapAnswer from "./tap-answer";
import TypedAnswer from "./typed-answer";
import type { AnswerProps } from "./types";

export type { AnswerProps };

const ANSWERS: Record<string, ComponentType<AnswerProps>> = {
  tap: TapAnswer,
  typed: TypedAnswer,
  spoken: SpokenAnswer,
};

export function answerFor(
  responseMode: string,
): ComponentType<AnswerProps> | null {
  return ANSWERS[responseMode] ?? null;
}

export const ANSWER_MODES = Object.keys(ANSWERS);
